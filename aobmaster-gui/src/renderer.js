import './index.css';
const { PROTOCOL_VERSION, SDK_VERSION, GUI_VERSION, buildRequest } = require('./ipc');

const state = {
  mutationMode: false,
  experimentalEnabled: false,
  auditLog: [],
  currentResult: null,
  currentSignatures: [],
  currentSignature: null,
};

const appendAudit = (entry) => {
  state.auditLog.push(entry);
  renderAuditLog();
};

const formatError = (response) => {
  if (!response) {
    return 'Unknown IPC error (no response payload).';
  }
  if (response.error) {
    const code = response.error.code ?? 'unknown';
    const message = response.error.message || 'SDK error';
    return `SDK error [${code}]: ${message}`;
  }
  return `Unexpected response format: ${JSON.stringify(response)}`;
};


const validateAnchorHex = (anchorValue, label) => {
  if (!anchorValue.startsWith('0x')) {
    return `${label} must be hex (e.g., 0x1000).`;
  }
  return null;
};

const validateSynthesisParams = (params) => {
  if (!params.base_binary) {
    return 'Base binary is required.';
  }
  if (!params.anchor_rva && !params.anchor_fo && !params.anchor_va) {
    return 'Anchor value is required.';
  }
  if (params.anchor_rva) {
    return validateAnchorHex(params.anchor_rva, 'Anchor RVA');
  }
  if (params.anchor_fo) {
    return validateAnchorHex(params.anchor_fo, 'Anchor file offset');
  }
  if (params.anchor_va) {
    return validateAnchorHex(params.anchor_va, 'Anchor virtual address');
  }
  return null;
};

const logRequest = (method, params) => {
  appendAudit(`[${new Date().toISOString()}] ${method} ${JSON.stringify(params)}`);
};

const callSdk = async (method, params) => {
  logRequest(method, params);
  const response = await window.aobmaster.ipcRequest(buildRequest(method, params));
  if (response.error) {
    throw new Error(`[${method}] ${formatError(response)}`);
  }
  return response.result;
};

const confirmStructuralRequest = async () => {
  if (!state.experimentalEnabled) {
    setStatus('Enable experimental features to use structural anchoring.', true);
    return false;
  }
  return window.confirm('Structural anchoring is experimental. Proceed?');
};


const setStatus = (message, isError = false) => {
  const statusEl = document.getElementById('status');
  statusEl.textContent = message;
  statusEl.className = isError ? 'status error' : 'status';
};

const toggleMutationMode = (enabled) => {
  state.mutationMode = enabled;
  renderMutationBanner();
};

const toggleExperimental = (enabled) => {
  state.experimentalEnabled = enabled;
  renderExperimentalBanner();
};

const renderMutationBanner = () => {
  const banner = document.getElementById('mutation-banner');
  if (state.mutationMode) {
    banner.textContent = 'Mutation Mode Enabled';
    banner.classList.add('active');
  } else {
    banner.textContent = 'Read-only mode (mutations disabled)';
    banner.classList.remove('active');
  }
};

const renderExperimentalBanner = () => {
  const banner = document.getElementById('experimental-banner');
  if (state.experimentalEnabled) {
    banner.textContent = 'Experimental features enabled';
    banner.classList.add('active');
  } else {
    banner.textContent = 'Experimental features disabled';
    banner.classList.remove('active');
  }
};

const renderAuditLog = () => {
  const list = document.getElementById('audit-log');
  list.innerHTML = '';
  state.auditLog.slice(-50).forEach((entry) => {
    const item = document.createElement('li');
    item.textContent = entry;
    list.appendChild(item);
  });
};

const getValue = (id) => document.getElementById(id).value.trim();

const gatherSynthesisParams = () => {
  const anchorType = document.querySelector('input[name="anchor-type"]:checked').value;
  const anchorValue = getValue('anchor-value');
  const anchorMode = getValue('anchor-mode');
  const params = {
    base_binary: getValue('base-binary'),
    version_binaries: getValue('version-binaries')
      ? getValue('version-binaries').split(',').map((p) => p.trim()).filter(Boolean)
      : [],
    align_mode: getValue('align-mode'),
    seed_bytes: Number(getValue('seed-bytes') || 32),
    seed_scan: getValue('seed-scan'),
    seed_allow_multi: document.getElementById('seed-allow-multi').checked,
    context_before: Number(getValue('context-before') || 8),
    context_after: Number(getValue('context-after') || 8),
    max_context_insns: Number(getValue('max-context-insns') || 32),
    context_variations: document.getElementById('context-variations').checked,
    profile: getValue('profile'),
    min_insns: Number(getValue('min-insns') || 6),
    max_insns: Number(getValue('max-insns') || 14),
    top_n: Number(getValue('top-n') || 5),
    require_unique: document.getElementById('require-unique').checked,
    require_present_all: document.getElementById('require-present-all').checked,
    scan_range: getValue('scan-range') || null,
    explain: document.getElementById('explain').checked,
    anchor_mode: anchorMode,
    structural_min_confidence: Number(getValue('structural-min-confidence') || 0.6),
    anchor_shift: Number(getValue('anchor-shift') || 0),
  };
  if (anchorType === 'rva') {
    params.anchor_rva = anchorValue;
  } else if (anchorType === 'fo') {
    params.anchor_fo = anchorValue;
  } else {
    params.anchor_va = anchorValue;
  }
  return params;
};

const mutationGuard = (reason) => {
  if (!state.mutationMode) {
    setStatus(`Enable mutation mode to ${reason}.`, true);
    return false;
  }
  return true;
};

const serializeSynthesisConfig = (params) => ({
  config: params,
  timestamp: new Date().toISOString(),
  gui_version: GUI_VERSION,
  sdk_version: SDK_VERSION,
});

const buildCliCommand = (params) => {
  const parts = ['aobmaster', 'synth', '--base', params.base_binary];
  if (params.anchor_rva) {
    parts.push('--anchor-rva', params.anchor_rva);
  }
  if (params.anchor_fo) {
    parts.push('--anchor-fo', params.anchor_fo);
  }
  if (params.anchor_va) {
    parts.push('--anchor-va', params.anchor_va);
  }
  if (params.version_binaries && params.version_binaries.length) {
    parts.push('--versions', ...params.version_binaries);
  }
  parts.push('--align', params.align_mode);
  parts.push('--seed-bytes', `${params.seed_bytes}`);
  parts.push('--seed-scan', params.seed_scan);
  parts.push('--seed-allow-multi', params.seed_allow_multi ? 'true' : 'false');
  parts.push('--context-before', `${params.context_before}`);
  parts.push('--context-after', `${params.context_after}`);
  parts.push('--max-context-insns', `${params.max_context_insns}`);
  parts.push('--context-variations', params.context_variations ? 'on' : 'off');
  parts.push('--profile', params.profile);
  parts.push('--min-insns', `${params.min_insns}`);
  parts.push('--max-insns', `${params.max_insns}`);
  parts.push('--top-n', `${params.top_n}`);
  if (params.scan_range) {
    parts.push('--scan-range', params.scan_range);
  }
  parts.push('--require-unique', params.require_unique ? 'true' : 'false');
  parts.push('--require-present-all', params.require_present_all ? 'true' : 'false');
  if (params.explain) {
    parts.push('--explain');
  }
  parts.push('--anchor-mode', params.anchor_mode);
  parts.push('--structural-min-confidence', `${params.structural_min_confidence}`);
  parts.push('--anchor-shift', `${params.anchor_shift}`);
  return parts.join(' ');
};

const renderSynthesisResult = () => {
  const container = document.getElementById('synthesis-result');
  const cli = document.getElementById('cli-preview');
  if (!state.currentResult) {
    container.textContent = 'No results yet.';
    cli.textContent = '';
    return;
  }
  const result = state.currentResult;
  cli.textContent = result.cli;
  const candidates = result.result?.candidates || [];
  const warnings = result.result?.warnings || [];
  const errors = result.result?.errors || [];
  const trace = result.result?.trace;
  let html = '';
  if (!result.result?.ok) {
    html += `<div class="error">SDK returned errors.</div>`;
  }
  if (errors.length) {
    html += `<div class="error">Errors: ${errors.map((e) => e.message).join(', ')}</div>`;
  }
  if (warnings.length) {
    html += `<div class="warning">Warnings: ${warnings.map((w) => w.message).join(', ')}</div>`;
  }
  if (trace && trace.truncated) {
    html += `<div class="warning">Trace truncated at ${trace.limit_bytes} bytes. Use export to file.</div>`;
  }
  html += `<table><thead><tr><th>Rank</th><th>Pattern</th><th>Score</th><th>Confidence</th><th>Valid</th><th>Score Breakdown</th><th>Experimental</th></tr></thead><tbody>`;
  candidates.forEach((cand, index) => {
    const score = cand.score?.score ?? 'n/a';
    const confidence = cand.score?.confidence ?? 'n/a';
    const scoreDetails = cand.score ? JSON.stringify(cand.score) : '';
    const experimental = state.currentResult?.result?.structural_anchor ? 'EXPERIMENTAL' : '';
    html += `<tr><td>${index + 1}</td><td class="mono">${cand.aob || ''}</td><td>${score}</td><td>${confidence}</td><td>${cand.valid ? 'yes' : 'no'}</td><td class="mono">${scoreDetails}</td><td>${experimental}</td></tr>`;
  });
  html += '</tbody></table>';
  if (trace) {
    html += `<pre class="trace">${JSON.stringify(trace, null, 2)}</pre>`;
    if (trace.truncated) {
      html += '<button id="export-trace">Export Trace</button>';
    }
  }
  container.innerHTML = html;
  if (trace && trace.truncated) {
    document.getElementById('export-trace').addEventListener('click', exportTrace);
  }
};

const exportTrace = async () => {
  const trace = state.currentResult?.result?.trace;
  if (!trace) {
    setStatus('No trace to export.', true);
    return;
  }
  const dialogResult = await window.aobmaster.saveFileDialog({
    title: 'Export trace',
    defaultPath: 'trace.json',
  });
  if (dialogResult.canceled || !dialogResult.filePath) {
    return;
  }
  const response = await window.aobmaster.exportConfig({
    output_path: dialogResult.filePath,
    payload: trace,
  });
  if (!response.ok) {
    setStatus(`Export failed: ${response.error}`, true);
    return;
  }
  setStatus(`Trace exported to ${dialogResult.filePath}`);
};

const openFilePicker = async () => {
  const dialogResult = await window.aobmaster.openFileDialog({
    properties: ['openFile'],
  });
  if (dialogResult.canceled || !dialogResult.filePaths.length) {
    return;
  }
  document.getElementById('base-binary').value = dialogResult.filePaths[0];
};

const renderSignatureList = () => {
  const list = document.getElementById('signature-list');
  list.innerHTML = '';
  if (!state.currentSignatures.length) {
    list.innerHTML = '<li>No signatures loaded.</li>';
    return;
  }
  state.currentSignatures.forEach((sig) => {
    const item = document.createElement('li');
    item.textContent = `${sig.id} — ${sig.name}`;
    item.addEventListener('click', () => {
      state.currentSignature = sig;
      renderSignatureDetail();
    });
    list.appendChild(item);
  });
};

const renderSignatureDetail = () => {
  const panel = document.getElementById('signature-detail');
  if (!state.currentSignature) {
    panel.textContent = 'Select a signature to view details.';
    return;
  }
  const sig = state.currentSignature;
  panel.innerHTML = `
    <div><strong>${sig.name}</strong> (${sig.id})</div>
    <div class="mono">Pattern: ${sig.pattern}</div>
    <div>Anchor RVA: ${sig.anchor_rva}</div>
    <div>Author: ${sig.author || 'unknown'}</div>
    <div>Version Range: ${sig.version_range || 'n/a'}</div>
  `;
};

const runSynthesis = async () => {
  const params = gatherSynthesisParams();
  setStatus('Running synthesis...');
  try {
    const validationError = validateSynthesisParams(params);
    if (validationError) {
      setStatus(validationError, true);
      return;
    }
    if (params.anchor_mode === 'structural') {
      const ok = await confirmStructuralRequest();
      if (!ok) {
        return;
      }
      setStatus('Structural anchoring (experimental) enabled for this run.');
    }
    const cli = buildCliCommand(params);
    const result = await callSdk('synthesizer.generate', params);
    state.currentResult = { result, cli };
    renderSynthesisResult();
    setStatus('Synthesis complete.');
  } catch (err) {
    setStatus(`Synthesis failed: ${err.message}`, true);
  }
};

const compareCliParity = async () => {
  if (!state.currentResult) {
    setStatus('Run synthesis first to compare CLI parity.', true);
    return;
  }
  setStatus('Comparing CLI parity...');
  const payload = {
    cli: state.currentResult.cli,
    gui: state.currentResult.result,
  };
  const dialogResult = await window.aobmaster.saveFileDialog({
    title: 'Save CLI parity snapshot',
    defaultPath: `cli_parity_${Date.now()}.json`,
  });
  if (dialogResult.canceled || !dialogResult.filePath) {
    return;
  }
  const response = await window.aobmaster.exportConfig({
    output_path: dialogResult.filePath,
    payload,
  });
  if (!response.ok) {
    setStatus(`CLI parity export failed: ${response.error}`, true);
    return;
  }
  setStatus('CLI parity snapshot saved.');
};

const cancelSdk = async () => {
  await window.aobmaster.cancelRequest();
  setStatus('SDK worker restarted.');
};

const exportSynthesisConfig = async () => {
  const params = gatherSynthesisParams();
  const dialogResult = await window.aobmaster.saveFileDialog({
    title: 'Export synthesis config',
    defaultPath: 'synthesis_config.json',
  });
  if (dialogResult.canceled || !dialogResult.filePath) {
    return;
  }
  const payload = serializeSynthesisConfig(params);
  const response = await window.aobmaster.exportConfig({
    output_path: dialogResult.filePath,
    payload,
  });
  if (!response.ok) {
    setStatus(`Export failed: ${response.error}`, true);
    return;
  }
  setStatus(`Config exported to ${dialogResult.filePath}`);
};

const previewCli = () => {
  const params = gatherSynthesisParams();
  document.getElementById('cli-preview').textContent = buildCliCommand(params);
};

const runSignatureList = async () => {
  const dbPath = getValue('db-path');
  if (!dbPath) {
    setStatus('Database path required.', true);
    return;
  }
  setStatus('Loading signatures...');
  try {
    const result = await callSdk('database.list_signatures', { db_path: dbPath, filter_text: getValue('db-filter') });
    state.currentSignatures = result.signatures || [];
    renderSignatureList();
    setStatus('Signatures loaded.');
  } catch (err) {
    setStatus(`Load failed: ${err.message}`, true);
  }
};

const runSignatureQuery = async () => {
  const dbPath = getValue('db-path');
  const sigId = getValue('db-signature-id');
  if (!dbPath || !sigId) {
    setStatus('Database path and signature ID required.', true);
    return;
  }
  setStatus('Querying signature...');
  try {
    const result = await callSdk('database.query_signature', { db_path: dbPath, signature_id: sigId });
    state.currentSignature = result.signature;
    renderSignatureDetail();
    setStatus('Signature loaded.');
  } catch (err) {
    setStatus(`Query failed: ${err.message}`, true);
  }
};

const runDatabaseExport = async () => {
  const dbPath = getValue('db-path');
  if (!dbPath) {
    setStatus('Database path required.', true);
    return;
  }
  const dialogResult = await window.aobmaster.saveFileDialog({
    title: 'Export signatures',
    defaultPath: 'signatures.json',
  });
  if (dialogResult.canceled) {
    return;
  }
  setStatus('Exporting signatures...');
  try {
    await callSdk('database.export_signatures', { db_path: dbPath, output_path: dialogResult.filePath });
    setStatus(`Exported to ${dialogResult.filePath}`);
  } catch (err) {
    setStatus(`Export failed: ${err.message}`, true);
  }
};

const runDatabaseImport = async () => {
  if (!mutationGuard('import signatures')) {
    return;
  }
  const dbPath = getValue('db-path');
  if (!dbPath) {
    setStatus('Database path required.', true);
    return;
  }
  const dialogResult = await window.aobmaster.openFileDialog({
    title: 'Import signatures',
    properties: ['openFile'],
  });
  if (dialogResult.canceled) {
    return;
  }
  if (!window.confirm('Import signatures into database?')) {
    return;
  }
  setStatus('Importing signatures...');
  try {
    await callSdk('database.import_signatures', { db_path: dbPath, input_path: dialogResult.filePaths[0] });
    setStatus('Import complete.');
  } catch (err) {
    setStatus(`Import failed: ${err.message}`, true);
  }
};

const runDatabaseInit = async () => {
  if (!mutationGuard('initialize database')) {
    return;
  }
  const dbPath = getValue('db-path');
  if (!dbPath) {
    setStatus('Database path required.', true);
    return;
  }
  if (!window.confirm('Initialize database?')) {
    return;
  }
  setStatus('Initializing database...');
  try {
    await callSdk('database.init', { db_path: dbPath });
    setStatus('Database initialized.');
  } catch (err) {
    setStatus(`Init failed: ${err.message}`, true);
  }
};

const runSaveSignature = async () => {
  if (!mutationGuard('save signatures')) {
    return;
  }
  if (!state.currentResult) {
    setStatus('Run synthesis first.', true);
    return;
  }
  const dbPath = getValue('db-path');
  const sigId = getValue('save-signature-id');
  const name = getValue('save-signature-name');
  if (!dbPath || !sigId || !name) {
    setStatus('Database path, signature ID, and name required.', true);
    return;
  }
  if (!window.confirm('Save signature to database?')) {
    return;
  }
  const candidates = Array.isArray(state.currentResult?.result?.candidates)
    ? state.currentResult.result.candidates
    : [];
  const top = candidates.find((cand) => cand.valid);
  const pattern = top?.aob || '';
  if (!pattern) {
    setStatus('No valid candidate pattern to save.', true);
    return;
  }
  const synthesisParams = gatherSynthesisParams();
  const resolvedRva = state.currentResult.result?.anchor?.resolved_base?.rva;
  const anchorValue = resolvedRva || synthesisParams.anchor_rva || synthesisParams.anchor_fo || synthesisParams.anchor_va || '';
  if (!anchorValue) {
    setStatus('Anchor value missing from synthesis parameters.', true);
    return;
  }
  const anchorLabel = resolvedRva
    ? 'Resolved anchor RVA'
    : synthesisParams.anchor_rva
      ? 'Anchor RVA'
      : synthesisParams.anchor_fo
        ? 'Anchor file offset'
        : 'Anchor virtual address';
  const anchorError = validateAnchorHex(anchorValue, anchorLabel);
  if (anchorError) {
    setStatus(anchorError, true);
    return;
  }
  setStatus('Saving signature...');
  try {
    await callSdk('database.save_signature', {
      db_path: dbPath,
      signature_id: sigId,
      name,
      pattern,
      anchor_rva: anchorValue,
      binary_hash: '',
      author: getValue('save-signature-author'),
      version_range: getValue('save-signature-version'),
      metadata: { gui_saved: true },
      parent_id: getValue('save-signature-parent') || null,
    });
    setStatus('Signature saved.');
  } catch (err) {
    setStatus(`Save failed: ${err.message}`, true);
  }
};

const runDeprecateSignature = async () => {
  if (!mutationGuard('deprecate signatures')) {
    return;
  }
  const dbPath = getValue('db-path');
  const sigId = getValue('deprecate-id');
  const reason = getValue('deprecate-reason');
  if (!dbPath || !sigId || !reason) {
    setStatus('Database path, signature ID, and reason required.', true);
    return;
  }
  if (!window.confirm('Deprecate signature?')) {
    return;
  }
  setStatus('Deprecating signature...');
  try {
    await callSdk('database.deprecate_signature', {
      db_path: dbPath,
      signature_id: sigId,
      reason,
    });
    setStatus('Signature deprecated.');
  } catch (err) {
    setStatus(`Deprecate failed: ${err.message}`, true);
  }
};

const runTests = async () => {
  if (!mutationGuard('run tests')) {
    return;
  }
  const dbPath = getValue('test-db-path');
  const corpus = getValue('test-corpus');
  if (!dbPath || !corpus) {
    setStatus('Database path and corpus pattern required.', true);
    return;
  }
  if (!window.confirm('Run tests?')) {
    return;
  }
  setStatus('Running tests...');
  try {
    const result = await callSdk('tester.test_all', {
      db_path: dbPath,
      corpus_pattern: corpus,
      signature_id: getValue('test-signature-id') || null,
      parallel: Number(getValue('test-parallel')),
      record: document.getElementById('test-record').checked,
    });
    document.getElementById('test-results').textContent = JSON.stringify(result, null, 2);
    setStatus('Tests complete.');
  } catch (err) {
    setStatus(`Tests failed: ${err.message}`, true);
  }
};

const runAnalyze = async () => {
  const dbPath = getValue('analysis-db-path');
  if (!dbPath) {
    setStatus('Database path required.', true);
    return;
  }
  setStatus('Running analysis...');
  try {
    const result = await callSdk('analyzer.analyze_all', { db_path: dbPath });
    document.getElementById('analysis-results').textContent = JSON.stringify(result, null, 2);
    setStatus('Analysis complete.');
  } catch (err) {
    setStatus(`Analysis failed: ${err.message}`, true);
  }
};

const bindEvents = () => {
  document.getElementById('mutation-toggle').addEventListener('change', (e) => {
    toggleMutationMode(e.target.checked);
  });
  document.getElementById('experimental-toggle').addEventListener('change', (e) => {
    toggleExperimental(e.target.checked);
  });
  document.getElementById('preview-cli').addEventListener('click', previewCli);
  document.getElementById('export-config').addEventListener('click', exportSynthesisConfig);
  document.getElementById('run-synthesis').addEventListener('click', runSynthesis);
  document.getElementById('cancel-synthesis').addEventListener('click', cancelSdk);
  document.getElementById('pick-base-binary').addEventListener('click', openFilePicker);
  document.getElementById('compare-cli').addEventListener('click', compareCliParity);
  document.getElementById('db-list').addEventListener('click', runSignatureList);
  document.getElementById('db-query').addEventListener('click', runSignatureQuery);
  document.getElementById('db-export').addEventListener('click', runDatabaseExport);
  document.getElementById('db-import').addEventListener('click', runDatabaseImport);
  document.getElementById('db-init').addEventListener('click', runDatabaseInit);
  document.getElementById('save-signature').addEventListener('click', runSaveSignature);
  document.getElementById('deprecate-signature').addEventListener('click', runDeprecateSignature);
  document.getElementById('run-tests').addEventListener('click', runTests);
  document.getElementById('run-analysis').addEventListener('click', runAnalyze);
};

const init = () => {
  renderMutationBanner();
  renderExperimentalBanner();
  renderAuditLog();
  renderSynthesisResult();
  renderSignatureDetail();
  bindEvents();
};

window.addEventListener('DOMContentLoaded', init);
