/* Smoke test de src/osia/web/app.js : DOM/fetch simulés, on vérifie que le script
 * se charge sans exception et rend la vue d'accueil dans #app. */
const fs = require('fs');
const assert = require('node:assert/strict');
const code = fs.readFileSync(process.argv[2], 'utf8');
const testSettings = process.argv.includes('--settings');
const byId = {};

function makeEl(tag) {
  const events = {};
  const el = {
    tagName: String(tag || 'div').toUpperCase(),
    children: [],
    style: {},
    dataset: {},
    value: '',
    checked: false,
    hidden: false,
    textContent: '',
    className: '',
    _html: '',
    setAttribute(k, v) {
      if (k === 'id') byId[v] = this;
      this[k] = v;
    },
    getAttribute(k) { return this[k] ?? null; }, setAttributeNS() {},
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    insertBefore(c) { this.children.unshift(c); return c; },
    replaceChildren() { this.children = []; },
    remove() {}, addEventListener(type, fn) { events[type] = fn; }, removeEventListener() {},
    async fire(type) { return events[type]({ target: this, preventDefault() {} }); },
    reportValidity() { return true; },
    focus() {}, click() {}, close() {}, showModal() {},
    querySelector() { return makeEl('div'); },
    querySelectorAll() { return []; },
    closest() { return null; },
    setPointerCapture() {},
    getBoundingClientRect() { return { width: 800, height: 600, left: 0, top: 0, right: 800, bottom: 600 }; },
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  };
  Object.defineProperty(el, 'innerHTML', { get() { return this._html; }, set(v) { this._html = String(v); } });
  Object.defineProperty(el, 'firstChild', { get() { return this.children[0] || null; } });
  return el;
}

global.document = {
  readyState: 'complete',
  getElementById(id) { if (!byId[id]) { byId[id] = makeEl('div'); byId[id].id = id; } return byId[id]; },
  querySelector(s) { return this.getElementById(String(s).replace(/^#/, '')); },
  querySelectorAll() { return []; },
  createElement(t) { return makeEl(t); },
  createElementNS(ns, t) { return makeEl(t); },
  createTextNode(t) { const e = makeEl('#text'); e.textContent = String(t); return e; },
  addEventListener() {},
  body: makeEl('body'),
  documentElement: makeEl('html'),
};
global.window = {
  addEventListener() {},
  location: { hash: testSettings ? '#/parametres' : '' },
  alert() {}, prompt() { return ''; }, open() { return null; }, confirm() { return true; },
};
global.location = global.window.location;
const store = { _s: {} };
global.sessionStorage = {
  getItem(k) { return Object.prototype.hasOwnProperty.call(store._s, k) ? store._s[k] : null; },
  setItem(k, v) { store._s[k] = String(v); },
  removeItem(k) { delete store._s[k]; },
};
global.window.sessionStorage = global.sessionStorage;

const responses = {
  '/api/v1/health': { status: 'ok', version: '0.1.0', mode: 'desktop' },
  '/api/v1/profiles': [],
  '/api/v1/investigations': [],
  '/api/v1/settings': { settings: {} },
  '/api/v1/secrets': { names: [] },
};
const providerState = {
  selected: 'simulated',
  configurations: { mistral: { base_url: 'https://api.mistral.ai/v1', model: 'initial-model', ready: false } },
};
const key = 'temporary-test-api-key';
global.fetch = async (url, options = {}) => {
  const u = String(url).split('?')[0];
  let body = Object.prototype.hasOwnProperty.call(responses, u) ? responses[u] : [];
  if (u === '/api/v1/ai/providers') body = providerState;
  if (u === '/api/v1/ai/providers/mistral/test') {
    assert.equal(options.method, 'POST');
    assert.equal(JSON.parse(options.body).api_key, key);
    body = { models: ['model-from-catalogue'] };
  }
  if (u === '/api/v1/ai/providers/mistral') {
    assert.equal(options.method, 'PUT');
    const saved = JSON.parse(options.body);
    assert.equal(saved.api_key, key);
    assert.equal(saved.model, 'model-from-catalogue');
    providerState.configurations.mistral.model = saved.model;
    providerState.configurations.mistral.ready = true;
    providerState.configurations.mistral.has_key = true;
    body = providerState;
  }
  if (u === '/api/v1/ai/selection/mistral') {
    assert.equal(options.method, 'PUT');
    providerState.selected = 'mistral';
    providerState.active_model = providerState.configurations.mistral.model;
    body = providerState;
  }
  return {
    ok: true, status: 200,
    headers: { get() { return 'application/json'; } },
    json: async () => body,
    text: async () => JSON.stringify(body),
    blob: async () => ({ size: 0 }),
    body: null,
  };
};

function dump(el, depth) {
  if (!el || depth > 6) return '';
  let out = el.textContent || '';
  for (const c of el.children || []) out += ' ' + dump(c, depth + 1);
  return out;
}

function find(node, predicate) {
  if (predicate(node)) return node;
  for (const child of node.children || []) {
    const found = find(child, predicate);
    if (found) return found;
  }
}

(async () => {
  try {
    eval(code);
  } catch (e) {
    console.log('SCRIPT CRASHED: ' + e.message);
    process.exit(1);
  }
  await new Promise((r) => setTimeout(r, 300));
  if (!global.window.OSIA) { console.log('NO OSIA EXPORT'); process.exit(1); }
  const app = byId['app'];
  if (testSettings) {
    const secret = byId['ai-key'];
    assert.equal(secret.type, 'password');
    secret.value = key;
    await find(app, n => n.textContent === 'Tester et lister les modèles').fire('click');
    assert.equal(byId['ai-models'].children[0].value, 'model-from-catalogue');
    byId['ai-model'].value = 'model-from-catalogue';
    await find(app, n => n.tagName === 'FORM').fire('submit');
    assert.equal(secret.value, '');
    await find(app, n => n.textContent === 'Utiliser ce fournisseur').fire('click');
    assert.match(dump(app, 0), /Fournisseur actif : Mistral API · model-from-catalogue/);
    assert.ok(!JSON.stringify(store._s).includes(key));
  }
  const rendered = dump(app, 0);
  console.log('SCRIPT OK');
  console.log(rendered);
})();
