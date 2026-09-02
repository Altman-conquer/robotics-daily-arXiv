const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const listeners = {};
const context = vm.createContext({
  window: { location: { search: '' } },
  document: { addEventListener: (name, callback) => { listeners[name] = callback; } },
  URLSearchParams,
  decodeURIComponent,
  console,
  setTimeout,
  clearTimeout,
});

vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'js', 'app.js'), 'utf8'), context);
vm.runInContext(`
  initEventListeners = () => {};
  fetchGitHubStats = () => {};
  loadUserKeywords = () => {};
  loadUserAuthors = () => {};
  fetchAvailableDates = async () => {};
`, context);

context.window.location.search = '?category=cs.RO';
listeners.DOMContentLoaded();
assert.equal(vm.runInContext('isJsonMode()', context), false);
assert.equal(vm.runInContext('currentCategory', context), 'cs.RO');

context.window.location.search = '?json=cs.RO';
assert.equal(vm.runInContext('isJsonMode()', context), true);
assert.equal(vm.runInContext('getJsonParam()', context), 'cs.RO');
