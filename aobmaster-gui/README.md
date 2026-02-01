# AoBMaster v2.3 GUI

This Electron-based GUI is a thin client over the AoBMaster SDK. It communicates with the
Python SDK worker via JSON-RPC and enforces read-only mode until mutation mode is explicitly
enabled. Structural anchoring is treated as experimental and requires an explicit toggle.

## Development

```bash
cd aobmaster-gui
npm install
npm start
```

The GUI expects `aobmaster/gui_worker.py` to be available relative to the repo root.
