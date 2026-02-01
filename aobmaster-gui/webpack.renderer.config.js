const baseRules = require('./webpack.rules');

// The shared `webpack.rules.js` includes loaders used to relocate native deps for
// the main process bundle. Those rules inject `__dirname` into the bundle, which
// breaks in the renderer since we intentionally run with `nodeIntegration: false`.
const rules = baseRules.filter((rule) => {
  if (rule?.use === 'node-loader') {
    return false;
  }
  if (rule?.use && typeof rule.use === 'object' && rule.use.loader === '@vercel/webpack-asset-relocator-loader') {
    return false;
  }
  return true;
});

rules.push({
  test: /\.css$/,
  use: [{ loader: 'style-loader' }, { loader: 'css-loader' }],
});

module.exports = {
  // Put your normal webpack config below here
  // Electron Forge serves/loads renderer HTML from `<entryName>/index.html`.
  // Using a publicPath of `../` makes injected asset URLs resolve correctly
  // for both dev server paths (`/main_window/index.html`) and packaged builds
  // loaded via `file://.../.webpack/renderer/main_window/index.html`.
  output: {
    publicPath: '../',
  },
  module: {
    rules,
  },
};
