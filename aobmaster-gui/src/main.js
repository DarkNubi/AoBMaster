const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const path = require('node:path');
const { spawn } = require('node:child_process');
const LINE_BREAK = '\n';
const fs = require('node:fs');
const os = require('node:os');

const PROTOCOL_VERSION = '1.0';
const SDK_VERSION = '2.0.0';
const TRACE_LIMIT_BYTES = 10 * 1024 * 1024;
const WORKER_ENV = {
  AOBMASTER_TRACE_LIMIT_BYTES: `${TRACE_LIMIT_BYTES}`,
};

let worker = null;
let workerBuffer = '';
const pending = new Map();
const auditLogPath = path.join(os.homedir(), '.aobmaster', 'gui_audit.log');

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (require('electron-squirrel-startup')) {
  app.quit();
}

const createWindow = () => {
  // Create the browser window.
  const mainWindow = new BrowserWindow({
    width: 1000,
    height: 720,
    webPreferences: {
      preload: MAIN_WINDOW_PRELOAD_WEBPACK_ENTRY,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // and load the index.html of the app.
  mainWindow.loadURL(MAIN_WINDOW_WEBPACK_ENTRY);
};

const resolveWorkerPath = () => {
  const candidates = [
    path.resolve(__dirname, '..', '..', '..', 'aobmaster', 'gui_worker.py'),
    path.resolve(__dirname, '..', '..', 'aobmaster', 'gui_worker.py'),
    path.resolve(process.cwd(), 'aobmaster', 'gui_worker.py'),
    path.resolve(process.cwd(), '..', 'aobmaster', 'gui_worker.py'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return candidates[0];
};

const stopWorker = () => {
  if (worker) {
    worker.kill();
    worker = null;
  }
  workerBuffer = '';
  pending.clear();
};

const startWorker = () => {
  stopWorker();
  const workerPath = resolveWorkerPath();
  const repoRoot = path.resolve(workerPath, '..', '..');
  worker = spawn(process.env.AOBMASTER_PYTHON || 'python', ['-m', 'aobmaster.gui_worker'], {
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, ...WORKER_ENV, PYTHONPATH: repoRoot },
  });
  worker.stdout.on('data', (chunk) => {
    workerBuffer += chunk.toString();
    let index;
    while ((index = workerBuffer.indexOf(LINE_BREAK)) >= 0) {
      const line = workerBuffer.slice(0, index).trim();
      workerBuffer = workerBuffer.slice(index + LINE_BREAK.length);
      if (!line) {
        continue;
      }
      try {
        const response = JSON.parse(line);
        const pendingRequest = pending.get(response.id);
        if (pendingRequest) {
          pendingRequest.resolve(response);
          pending.delete(response.id);
        }
      } catch (err) {
        console.error('Failed to parse worker response', err);
      }
    }
  });
  worker.stderr.on('data', (chunk) => {
    console.error('SDK worker stderr:', chunk.toString());
  });
  worker.on('exit', () => {
    for (const { reject } of pending.values()) {
      reject(new Error('SDK worker exited'));
    }
    pending.clear();
  });
};

const sendToWorker = (request) => {
  if (!worker) {
    startWorker();
  }
  return new Promise((resolve, reject) => {
    pending.set(request.id, { resolve, reject });
    worker.stdin.write(`${JSON.stringify(request)}${LINE_BREAK}`);
  });
};

const logAuditEntry = (payload) => {
  try {
    fs.mkdirSync(path.dirname(auditLogPath), { recursive: true });
    const entry = `[${new Date().toISOString()}] ${payload.method} ${JSON.stringify(payload.params || {})}${LINE_BREAK}`;
    fs.appendFileSync(auditLogPath, entry);
  } catch (err) {
    console.error('Failed to write audit log', err);
  }
};

const ensureVersionHandshake = async () => {
  const response = await sendToWorker({
    jsonrpc: '2.0',
    protocol_version: PROTOCOL_VERSION,
    sdk_version: SDK_VERSION,
    id: `handshake-${Date.now()}`,
    method: 'system.versions',
    params: {},
  });
  if (response.error) {
    throw new Error(response.error.message || 'Protocol mismatch');
  }
  const result = response.result || {};
  if (result.protocol_version !== PROTOCOL_VERSION) {
    throw new Error('SDK protocol version mismatch');
  }
  if (result.sdk_version.split('.')[0] !== SDK_VERSION.split('.')[0]) {
    throw new Error('SDK version mismatch');
  }
};

ipcMain.handle('aobmaster:request', async (_event, payload) => {
  try {
    if (payload?.method) {
      logAuditEntry(payload);
    }
    await ensureVersionHandshake();
    const response = await sendToWorker(payload);
    return response;
  } catch (err) {
    return {
      jsonrpc: '2.0',
      protocol_version: PROTOCOL_VERSION,
      sdk_version: SDK_VERSION,
      id: payload.id,
      error: { code: -32099, message: err.message || 'IPC error' },
    };
  }
});

ipcMain.handle('aobmaster:open-file', async (_event, options) => {
  return dialog.showOpenDialog(options || {});
});

ipcMain.handle('aobmaster:save-file', async (_event, options) => {
  return dialog.showSaveDialog(options || {});
});

ipcMain.handle('aobmaster:export-config', async (_event, payload) => {
  try {
    const resolved = path.resolve(payload.output_path);
    fs.writeFileSync(resolved, JSON.stringify(payload.payload, null, 2));
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle('aobmaster:cancel', async () => {
  stopWorker();
  startWorker();
  return { ok: true };
});

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.whenReady().then(() => {
  startWorker();
  createWindow();

  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopWorker();
    app.quit();
  }
});

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and import them here.
