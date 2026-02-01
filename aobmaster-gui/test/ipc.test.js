const assert = require('node:assert');

const { buildRequest, PROTOCOL_VERSION, SDK_VERSION } = require('../src/ipc');

const request = buildRequest('synthesizer.generate', { base_binary: 'demo.exe' });

assert.strictEqual(request.jsonrpc, '2.0');
assert.strictEqual(request.protocol_version, PROTOCOL_VERSION);
assert.strictEqual(request.sdk_version, SDK_VERSION);
assert.strictEqual(request.method, 'synthesizer.generate');

console.log('IPC request builder test passed.');
