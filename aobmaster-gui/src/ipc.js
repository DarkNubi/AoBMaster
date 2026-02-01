const PROTOCOL_VERSION = '1.0';
const SDK_VERSION = '2.0.0';

const buildRequest = (method, params) => ({
  jsonrpc: '2.0',
  protocol_version: PROTOCOL_VERSION,
  sdk_version: SDK_VERSION,
  id: `req-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  method,
  params,
});

module.exports = {
  PROTOCOL_VERSION,
  SDK_VERSION,
  buildRequest,
};
