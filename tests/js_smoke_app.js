/* Smoke test de src/osia/web/app.js : DOM/fetch simulés, on vérifie que le script
 * se charge sans exception et rend la vue d'accueil dans #app. */
const fs = require('fs');
const code = fs.readFileSync(process.argv[2], 'utf8');

function makeEl(tag) {
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
    setAttribute() {}, getAttribute() { return null; }, setAttributeNS() {},
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    insertBefore(c) { this.children.unshift(c); return c; },
    replaceChildren() { this.children = []; },
    remove() {}, addEventListener() {}, removeEventListener() {},
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

const byId = {};
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
  location: { hash: '' },
  alert() {}, prompt() { return ''; }, open() { return null; },
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
};
global.fetch = async (url) => {
  const u = String(url).split('?')[0];
  const body = Object.prototype.hasOwnProperty.call(responses, u) ? responses[u] : [];
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
  const rendered = dump(app, 0);
  console.log('SCRIPT OK');
  console.log(rendered);
})();
