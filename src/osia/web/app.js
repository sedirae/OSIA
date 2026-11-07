/* OSIA — interface web (lot C). Client vanilla de l'API /api/v1.
 * Règle de sécurité : aucune donnée externe n'est jamais injectée par innerHTML
 * (T5.6) ; tout contenu collecté passe par textContent/createElement. */
(function () {
  'use strict';

  var storage = (function () {
    try { return window.sessionStorage; } catch (e) { return { getItem: function () { return null; }, setItem: function () {}, removeItem: function () {} }; }
  })();

  var SUPPORT_LABEL = { documente: 'documenté', corrobore: 'corrobore', a_confirmer: 'à confirmer', contradictoire: 'contradictoire', non_etabli: 'non établi' };
  var HUMAN_LABEL = { unexamined: 'non examiné', validated: 'validé', rejected: 'rejeté' };
  var NATURE_LABEL = { fait_etabli: 'fait établi', information_rapportee: 'information rapportée', indice: 'indice', hypothese: 'hypothèse', conclusion_analytique: 'conclusion analytique' };
  var STATE_LABEL = { created: 'non lancée', running: 'en cours', suspended: 'suspendue', stopped: 'arrêtée', error: 'en erreur' };
  var STOP_LABEL = { objective_suffisamment_etaye: 'objectif suffisamment étayé', depth_limit: 'limite de profondeur', budget_exhausted: 'budget épuisé', sources_exhausted: 'sources épuisées', user_interrupt: 'arrêt demandé par l’utilisateur', technical_error: 'erreur technique', security_block: 'blocage sécurité' };
  var KIND_COLORS = { personne: '#2458C6', organisation: '#6B4FA1', adresse: '#0E7C7B', domaine: '#B3261E', document: '#8A5A00', evenement: '#1E7B34', autre: '#5A6478' };

  var state = {
    token: storage.getItem('osia_token') || '',
    mode: 'desktop',
    invId: null,
    inv: null, branches: [], graph: { entities: [], relations: [] }, assertions: [], decisions: [], proofs: [], budget: null, tasks: [], objectif: null, matches: [],
    branchFilter: null,
    graphMode: 'reseau',
    filters: { query: '', hideRejected: false, kinds: {} },
    positions: {},
    view: { x: 0, y: 0, k: 1 },
    journal: [],
    layoutSig: null,
    selected: null,
    cursor: 0,
    sseAbort: null,
    lastObjectiveAt: null,
    refreshTimer: null
  };

  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'class') node.className = attrs[k];
        else if (k === 'text') node.textContent = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) { if (c != null) node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function authHeaders() { var h = {}; if (state.token) h['Authorization'] = 'Bearer ' + state.token; return h; }
  function showAuth() {
    var d = $('auth-dialog');
    if (d && d.showModal) d.showModal();
    var b = $('auth-button');
    if (b) b.hidden = false;
  }
  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({}, authHeaders(), opts.headers || {});
    var resp = await fetch(path, opts);
    if (resp.status === 401) { showAuth(); var err = new Error('unauthorized'); err.status = 401; throw err; }
    return resp;
  }
  async function apiJson(path, opts) {
    var r = await api(path, opts);
    if (!r.ok) {
      var body = null;
      try { body = await r.json(); } catch (e) { body = null; }
      var msg = body && body.error ? body.error.code + ': ' + body.error.message : ('HTTP ' + r.status);
      var err = new Error(msg); err.status = r.status; err.body = body; throw err;
    }
    return r.json();
  }
  function badge(text, cls) { return el('span', { class: 'badge ' + (cls || '') }, [text]); }
  function fmtDate(iso) { if (!iso) return ''; var d = new Date(iso); return isNaN(d) ? String(iso) : d.toLocaleString('fr-FR'); }
  function fmtCents(c) { return ((c || 0) / 100).toFixed(2) + ' €'; }
  function entityLabel(e) { var d = e.data || {}; return d.name || d.label || d.title || d.value || d.url || e.id; }
  function kindColor(kind) { return KIND_COLORS[kind] || '#5A6478'; }
  function uuid() { return (crypto.randomUUID ? crypto.randomUUID() : 'k-' + Date.now() + '-' + Math.random().toString(16).slice(2)); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function bindAuth() {
    var form = $('auth-form');
    if (form) form.addEventListener('submit', function () {
      state.token = $('auth-token').value;
      storage.setItem('osia_token', state.token);
      var d = $('auth-dialog');
      if (d && d.close) d.close();
      init();
    });
    var cancel = $('auth-cancel');
    if (cancel) cancel.addEventListener('click', function () { var d = $('auth-dialog'); if (d && d.close) d.close(); });
    var ab = $('auth-button');
    if (ab) ab.addEventListener('click', showAuth);
  }

  function parseRoute() {
    var h = (window.location.hash || '#/').replace(/^#/, '');
    var m = h.match(/^\/inv\/(.+)$/);
    if (!m) return { name: 'home' };
    var id = m[1];
    try { id = decodeURIComponent(id); } catch (e) { return { name: 'home' }; }
    return { name: 'inv', id: id };
  }
  async function renderRoute() {
    var route = parseRoute();
    if (route.name === 'inv') await renderInvestigation(route.id);
    else await renderHome();
  }

  async function init() {
    try {
      var h = await apiJson('/api/v1/health');
      state.mode = h.mode || 'desktop';
    } catch (e) { return; }
    var mb = $('mode-badge');
    if (mb) {
      mb.textContent = state.mode === 'server' ? 'mode serveur' : 'mode desktop';
      mb.className = 'badge' + (state.mode === 'server' ? ' a_confirmer' : ' documente');
    }
    var ab = $('auth-button');
    if (ab && state.mode === 'server') ab.hidden = false;
    await renderRoute();
  }

  async function renderHome() {
    state.invId = null;
    var app = $('app');
    if (!app) return;
    clear(app);
    var form = el('form', { class: 'card', id: 'new-inv' });
    form.appendChild(el('h1', { text: 'Nouvelle investigation' }));
    form.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Titre' }), el('input', { type: 'text', name: 'title', required: 'required' })]));
    form.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Objectif (facultatif, langage naturel)' }), el('textarea', { name: 'objective' })]));
    form.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Indices de départ (un par ligne : nom, organisation, adresse, identifiant…)' }), el('textarea', { name: 'hints', required: 'required' })]));
    var det = el('details', {});
    det.appendChild(el('summary', { text: 'Paramètres avancés (profil, limites)' }));
    det.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Profil' }), el('select', { name: 'profile_id', id: 'profile-select' })]));
    ['max_rebonds', 'max_source_requests', 'max_ai_calls', 'max_duration_seconds', 'max_cost_cents'].forEach(function (k) {
      det.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Surcharge ' + k + ' (vide = profil)' }), el('input', { type: 'number', name: 'lim_' + k, min: '0' })]));
    });
    form.appendChild(det);
    form.appendChild(el('button', { type: 'submit', class: 'primary', text: 'Lancer la recherche' }));
    form.appendChild(el('p', { class: 'muted small', id: 'home-error', role: 'alert' }));
    app.appendChild(form);

    var listCard = el('section', { class: 'card' });
    listCard.appendChild(el('h2', { text: 'Investigations' }));
    var ul = el('ul', { class: 'plain', id: 'inv-list' });
    listCard.appendChild(ul);
    app.appendChild(listCard);

    try {
      var profiles = await apiJson('/api/v1/profiles');
      var sel = $('profile-select');
      if (sel) profiles.forEach(function (p) {
        var o = el('option', { value: p.id, text: p.name + (p.is_default ? ' (défaut)' : '') });
        if (p.is_default) o.setAttribute('selected', 'selected');
        sel.appendChild(o);
      });
    } catch (e) { /* profils indisponibles */ }

    try {
      var invs = await apiJson('/api/v1/investigations');
      clear(ul);
      if (!invs.length) ul.appendChild(el('li', { class: 'muted', text: 'Aucune investigation pour le moment.' }));
      invs.forEach(function (inv) {
        var li = el('li', {});
        li.appendChild(el('a', { href: '#/inv/' + encodeURIComponent(inv.id), text: inv.title || inv.id }));
        li.appendChild(document.createTextNode(' '));
        li.appendChild(badge(STATE_LABEL[inv.state] || inv.state, inv.state === 'running' ? 'running' : inv.state === 'error' ? 'error' : 'stopped'));
        if (inv.stop_reason) li.appendChild(document.createTextNode(' — ' + (STOP_LABEL[inv.stop_reason] || inv.stop_reason)));
        ul.appendChild(li);
      });
    } catch (e) { if (e.status !== 401) ul.appendChild(el('li', { class: 'muted', text: 'Liste indisponible : ' + e.message })); }

    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      var fd = new FormData(form);
      var limits = {};
      ['max_rebonds', 'max_source_requests', 'max_ai_calls', 'max_duration_seconds', 'max_cost_cents'].forEach(function (k) {
        var v = fd.get('lim_' + k);
        if (v !== null && v !== '') limits[k] = Number(v);
      });
      var body = {
        title: String(fd.get('title') || '').trim(),
        objective: String(fd.get('objective') || '').trim() || null,
        hints: String(fd.get('hints') || '').split('\n').map(function (s) { return s.trim(); }).filter(Boolean),
        profile_id: String(fd.get('profile_id') || 'rapide'),
        idempotency_key: uuid()
      };
      if (Object.keys(limits).length) body.limits = limits;
      try {
        var r = await api('/api/v1/investigations', {
          method: 'POST',
          headers: Object.assign({ 'Content-Type': 'application/json', 'Idempotency-Key': body.idempotency_key }, authHeaders()),
          body: JSON.stringify(body)
        });
        if (!r.ok) {
          var j = await r.json().catch(function () { return null; });
          throw new Error(j && j.error ? j.error.message : 'HTTP ' + r.status);
        }
        var inv = await r.json();
        window.location.hash = '#/inv/' + encodeURIComponent(inv.id);
      } catch (e) {
        if (e.status === 401) return;
        var he = $('home-error');
        if (he) he.textContent = 'Lancement refusé : ' + e.message;
      }
    });
  }

  async function loadInvestigationData(id) {
    var base = '/api/v1/investigations/' + encodeURIComponent(id);
    var q = state.branchFilter ? '?branch_id=' + encodeURIComponent(state.branchFilter) : '';
    var results = await Promise.all([
      apiJson(base),
      apiJson(base + '/branches'),
      apiJson(base + '/graph?limit=500' + (state.branchFilter ? '&branch_id=' + encodeURIComponent(state.branchFilter) : '')),
      apiJson(base + '/assertions?include_superseded=true' + (state.branchFilter ? '&branch_id=' + encodeURIComponent(state.branchFilter) : '')),
      apiJson(base + '/decisions'),
      apiJson(base + '/proofs'),
      apiJson(base + '/budget'),
      apiJson(base + '/tasks'),
      apiJson(base + '/objectif' + q),
      apiJson(base + '/matches')
    ]);
    state.inv = results[0]; state.branches = results[1]; state.graph = results[2];
    state.assertions = results[3]; state.decisions = results[4]; state.proofs = results[5];
    state.budget = results[6]; state.tasks = results[7]; state.objectif = results[8]; state.matches = results[9];
  }

  async function renderInvestigation(id) {
    state.invId = id;
    if (state.sseAbort) { state.sseAbort.abort(); state.sseAbort = null; }
    try { await loadInvestigationData(id); }
    catch (e) {
      if (e.status === 401) return;
      var app = $('app');
      if (!app) return;
      clear(app);
      app.appendChild(el('p', { class: 'muted', role: 'alert', text: 'Investigation indisponible : ' + e.message }));
      return;
    }
    var stored = null;
    try { stored = storage.getItem('osia_pos_' + id); } catch (err) { stored = null; }
    try { state.positions = stored ? JSON.parse(stored) : {}; } catch (err) { state.positions = {}; }
    state.cursor = 0;
    state.journal = [];
    state.view = { x: 0, y: 0, k: 1 };
    state.layoutSig = null;
    renderLayout();
    startEvents(id);
  }

  function renderLayout() {
    var app = $('app');
    if (!app) return;
    clear(app);
    var inv = state.inv;
    if (!inv) return;
    var layout = el('div', { class: 'layout', id: 'layout' });
    var colSuivi = el('section', { class: 'col-suivi card', 'aria-label': 'Suivi' });
    var colGraphe = el('section', { class: 'col-graphe' });
    var colFiche = el('aside', { class: 'col-fiche card', id: 'fiche', 'aria-label': 'Fiche contextuelle' });
    layout.appendChild(colSuivi); layout.appendChild(colGraphe); layout.appendChild(colFiche);
    app.appendChild(layout);

    colSuivi.appendChild(el('h1', { text: inv.title }));
    if (inv.objective) colSuivi.appendChild(el('p', { class: 'small muted', text: 'Objectif : ' + inv.objective }));
    var badgesRow = el('p', {});
    badgesRow.appendChild(badge(STATE_LABEL[inv.state] || inv.state, inv.state === 'running' ? 'running' : inv.state === 'error' ? 'error' : 'stopped'));
    if (inv.stop_reason) {
      badgesRow.appendChild(document.createTextNode(' '));
      badgesRow.appendChild(badge(STOP_LABEL[inv.stop_reason] || inv.stop_reason, 'a_confirmer'));
    }
    colSuivi.appendChild(badgesRow);

    var actions = el('p', { class: 'row' });
    var stopBtn = el('button', { type: 'button', class: 'danger', text: 'Arrêter' });
    stopBtn.addEventListener('click', async function () {
      try {
        await apiJson('/api/v1/investigations/' + inv.id + '/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: 'user_interrupt' }) });
        await refreshData();
      } catch (e) { if (e.status !== 401) window.alert(e.message); }
    });
    var resumeBtn = el('button', { type: 'button', text: 'Reprendre' });
    resumeBtn.addEventListener('click', async function () {
      try { await apiJson('/api/v1/investigations/' + inv.id + '/resume', { method: 'POST' }); await refreshData(); }
      catch (e) { if (e.status !== 401) window.alert(e.message); }
    });
    actions.appendChild(stopBtn); actions.appendChild(resumeBtn);
    actions.appendChild(el('a', { href: '#/', text: '← Toutes les investigations' }));
    colSuivi.appendChild(actions);

    colSuivi.appendChild(el('h2', { text: 'Consommation réelle' }));
    colSuivi.appendChild(el('div', { id: 'budget-box' }));
    renderBudget();

    colSuivi.appendChild(el('h2', { text: 'Journal des opérations' }));
    colSuivi.appendChild(el('ul', { id: 'journal', 'aria-live': 'polite' }));
    state.journal.forEach(function (ev) { appendJournal(ev, true); });

    colSuivi.appendChild(el('h2', { text: 'Tâches' }));
    colSuivi.appendChild(el('ul', { class: 'plain small', id: 'task-list' }));
    renderTasks();

    renderBranches(colGraphe);
    renderGraphToolbar(colGraphe);
    var SVG_NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('id', 'graph-svg');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Graphe relationnel');
    colGraphe.appendChild(svg);
    renderGraph(svg);
    colGraphe.appendChild(el('h2', { text: 'Synthèse' }));
    var synth = el('div', { id: 'synthese' });
    colGraphe.appendChild(synth);
    renderSynthese(synth);
    colGraphe.appendChild(el('h2', { text: 'Rapprochements proposés (supervisés)' }));
    var matches = el('div', { id: 'matches' });
    colGraphe.appendChild(matches);
    renderMatches(matches);
    colGraphe.appendChild(el('h2', { text: 'Restitution (manuelle)' }));
    var rest = el('div', { id: 'restitution' });
    colGraphe.appendChild(rest);
    renderRestitution(rest);

    colFiche.appendChild(el('p', { class: 'muted', text: 'Sélectionnez un nœud ou une relation du graphe.' }));
  }

  function renderBudget() {
    var box = $('budget-box');
    if (!box || !state.budget) return;
    clear(box);
    var b = state.budget;
    var t = el('table', { class: 'mini' });
    [['Consommé (réel)', fmtCents(b.consumed_cents)], ['Réservé (engagé)', fmtCents(b.reserved_cents)], ['Estimé', fmtCents(b.estimated_cents)], ['Disponible', fmtCents(b.available_cents)], ['Plafond investigation', fmtCents(b.caps && b.caps.investigation)], ['Plafond global mois', fmtCents(b.caps && b.caps.global_month)]].forEach(function (row) {
      t.appendChild(el('tr', {}, [el('th', { text: row[0] }), el('td', { text: row[1] })]));
    });
    box.appendChild(t);
    box.appendChild(el('p', { class: 'small muted', text: 'Aucun pourcentage de progression n’est affiché : la complétude d’une investigation exploratoire n’est pas mesurable de façon fiable (C2-10).' }));
  }

  function renderTasks() {
    var ul = $('task-list');
    if (!ul) return;
    clear(ul);
    state.tasks.slice(0, 50).forEach(function (t) {
      ul.appendChild(el('li', { text: t.kind + ' — ' + t.state + (t.depth != null ? ' (profondeur ' + t.depth + ')' : '') + (t.error ? ' : ' + t.error : '') }));
    });
    if (!state.tasks.length) ul.appendChild(el('li', { class: 'muted', text: 'Aucune tâche.' }));
  }

  function renderBranches(col) {
    var card = el('div', { class: 'card', id: 'branches-card' });
    card.appendChild(el('h2', { text: 'Arbre des investigations (distinct du graphe relationnel)' }));
    var byParent = {};
    state.branches.forEach(function (b) { var k = b.parent_branch_id || ''; (byParent[k] = byParent[k] || []).push(b); });
    function branchNode(b) {
      var div = el('div', { class: 'branche' + (state.branchFilter === b.id ? ' active' : '') });
      var head = el('p', { class: 'branche-head' });
      var btn = el('button', { type: 'button', class: 'clickable', text: (b.objective || b.id) + ' [' + (STATE_LABEL[b.state] || b.state) + ']' });
      btn.addEventListener('click', function () { state.branchFilter = (state.branchFilter === b.id ? null : b.id); refreshData(); });
      head.appendChild(btn);
      if (b.stop_reason) head.appendChild(document.createTextNode(' — ' + (STOP_LABEL[b.stop_reason] || b.stop_reason)));
      div.appendChild(head);
      (byParent[b.id] || []).forEach(function (c) { div.appendChild(branchNode(c)); });
      return div;
    }
    (byParent[''] || []).forEach(function (b) { card.appendChild(branchNode(b)); });
    var newBranch = el('details', {});
    newBranch.appendChild(el('summary', { text: 'Approfondir (branche explicite, jamais automatique — C7-05)' }));
    var f = el('form', {});
    f.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Objectif de la branche' }), el('input', { type: 'text', name: 'objective', required: 'required' })]));
    f.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Surcharge max_rebonds (vide = profil)' }), el('input', { type: 'number', name: 'max_rebonds', min: '1', max: '10' })]));
    f.appendChild(el('label', {}, [el('input', { type: 'checkbox', name: 'accept', required: 'required' }), document.createTextNode(' J’accepte explicitement les limites de cette branche (C7-06)')]));
    f.appendChild(el('button', { type: 'submit', class: 'primary', text: 'Lancer la branche' }));
    f.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      var fd = new FormData(f);
      var body = { objective: String(fd.get('objective')), explicit_acceptance: true, idempotency_key: uuid() };
      var mr = fd.get('max_rebonds');
      if (mr) body.limits = { max_rebonds: Number(mr) };
      try {
        await apiJson('/api/v1/investigations/' + state.invId + '/branches', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        await refreshData();
      } catch (e) { if (e.status !== 401) window.alert('Branche refusée : ' + e.message); }
    });
    newBranch.appendChild(f);
    card.appendChild(newBranch);
    col.appendChild(card);
  }

  function renderGraphToolbar(col) {
    var bar = el('div', { class: 'toolbar', id: 'graph-toolbar' });
    ['reseau', 'arborescent', 'regroupe'].forEach(function (m) {
      var b = el('button', { type: 'button', text: m, 'aria-pressed': String(state.graphMode === m) });
      if (state.graphMode === m) b.className = 'primary';
      b.addEventListener('click', function () { state.graphMode = m; var s = $('graph-svg'); if (s) { clear(s); renderGraph(s); } });
      bar.appendChild(b);
    });
    var q = el('input', { type: 'search', placeholder: 'Rechercher une entité…', 'aria-label': 'Rechercher une entité', id: 'graph-query' });
    q.value = state.filters.query;
    q.addEventListener('input', function () { state.filters.query = q.value; var s = $('graph-svg'); if (s) { clear(s); renderGraph(s); } });
    bar.appendChild(q);
    var hide = el('label', {}, [el('input', { type: 'checkbox', id: 'graph-hide-rejected' }), document.createTextNode(' masquer les relations rejetées (restent consultables, C4-16)')]);
    var hcb = hide.querySelector('input');
    hcb.checked = state.filters.hideRejected;
    hcb.addEventListener('change', function (e) { state.filters.hideRejected = e.target.checked; var s = $('graph-svg'); if (s) { clear(s); renderGraph(s); } });
    bar.appendChild(hide);
    var kinds = {};
    state.graph.entities.forEach(function (e) { kinds[e.kind] = true; });
    Object.keys(kinds).sort().forEach(function (k) {
      var lab = el('label', {}, [el('input', { type: 'checkbox' }), document.createTextNode(' ' + k)]);
      var cb = lab.querySelector('input');
      cb.checked = state.filters.kinds[k] !== false;
      cb.addEventListener('change', function (e) { state.filters.kinds[k] = e.target.checked; var s = $('graph-svg'); if (s) { clear(s); renderGraph(s); } });
      bar.appendChild(lab);
    });
    bar.appendChild(el('span', { id: 'graph-counter' }));
    col.appendChild(bar);
  }

  function visibleEntities() {
    var q = (state.filters.query || '').toLowerCase();
    return state.graph.entities.filter(function (e) {
      if (e.merged_into) return false;
      if (state.filters.kinds[e.kind] === false) return false;
      if (q && entityLabel(e).toLowerCase().indexOf(q) < 0 && e.id.toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
  }
  function visibleRelations(visIds) {
    var ids = {};
    visIds.forEach(function (e) { ids[e.id] = true; });
    return state.graph.relations.filter(function (r) {
      if (!ids[r.src_id] || !ids[r.dst_id]) return false;
      if (state.filters.hideRejected && r.human_decision === 'rejected') return false;
      return true;
    });
  }

  function layoutSignature() {
    return state.graphMode + '|' + state.graph.entities.map(function (e) { return e.id; }).sort().join(',');
  }

  function computePositions(entities, relations) {
    var pos = state.positions;
    var n = entities.length;
    var fresh = false;
    entities.forEach(function (e, i) {
      if (!pos[e.id]) {
        fresh = true;
        var a = (2 * Math.PI * i) / Math.max(n, 1);
        pos[e.id] = { x: 400 + 260 * Math.cos(a), y: 300 + 200 * Math.sin(a), fixed: false };
      }
    });
    var sig = layoutSignature();
    var run = fresh || sig !== state.layoutSig;
    state.layoutSig = sig;
    if (!run) return pos;
    if (state.graphMode === 'arborescent') {
      var incoming = {};
      relations.forEach(function (r) { incoming[r.dst_id] = true; });
      var roots = entities.filter(function (e) { return !incoming[e.id]; });
      if (!roots.length && entities.length) roots = [entities[0]];
      var level = {}; var queue = [];
      roots.forEach(function (r) { level[r.id] = 0; queue.push(r.id); });
      var children = {};
      relations.forEach(function (r) { (children[r.src_id] = children[r.src_id] || []).push(r.dst_id); });
      while (queue.length) {
        var cur = queue.shift();
        (children[cur] || []).forEach(function (c) { if (level[c] === undefined) { level[c] = level[cur] + 1; queue.push(c); } });
      }
      var byLevel = {};
      entities.forEach(function (e) { var l = level[e.id] === undefined ? 0 : level[e.id]; (byLevel[l] = byLevel[l] || []).push(e); });
      Object.keys(byLevel).forEach(function (l) {
        byLevel[l].forEach(function (e, i) {
          if (pos[e.id] && pos[e.id].fixed) return;
          pos[e.id] = { x: 80 + Number(l) * 190, y: 60 + i * 80, fixed: false };
        });
      });
    } else if (state.graphMode === 'regroupe') {
      var byKind = {};
      entities.forEach(function (e) { (byKind[e.kind] = byKind[e.kind] || []).push(e); });
      var kinds = Object.keys(byKind);
      kinds.forEach(function (k, gi) {
        var cx = 400 + 300 * Math.cos((2 * Math.PI * gi) / Math.max(kinds.length, 1));
        var cy = 300 + 240 * Math.sin((2 * Math.PI * gi) / Math.max(kinds.length, 1));
        byKind[k].forEach(function (e, i) {
          if (pos[e.id] && pos[e.id].fixed) return;
          var a = (2 * Math.PI * i) / Math.max(byKind[k].length, 1);
          pos[e.id] = { x: cx + 90 * Math.cos(a), y: cy + 70 * Math.sin(a), fixed: false };
        });
      });
    } else {
      for (var it = 0; it < 60; it++) {
        var k = 1 - it / 60;
        entities.forEach(function (a) {
          var pa = pos[a.id];
          if (pa.fixed) return;
          entities.forEach(function (b) {
            if (a === b) return;
            var pb = pos[b.id];
            var dx = pa.x - pb.x, dy = pa.y - pb.y;
            var d2 = dx * dx + dy * dy + 0.01;
            var f = (2600 * k) / d2;
            pa.x += dx * f * 0.01; pa.y += dy * f * 0.01;
          });
        });
        relations.forEach(function (r) {
          var ps = pos[r.src_id], pd = pos[r.dst_id];
          if (!ps || !pd) return;
          var dx = pd.x - ps.x, dy = pd.y - ps.y;
          var d = Math.sqrt(dx * dx + dy * dy) || 1;
          var f = (d - 120) * 0.02 * k;
          if (!ps.fixed) { ps.x += dx / d * f; ps.y += dy / d * f; }
          if (!pd.fixed) { pd.x -= dx / d * f; pd.y -= dy / d * f; }
        });
        entities.forEach(function (e) { var p = pos[e.id]; p.x = Math.max(40, Math.min(760, p.x)); p.y = Math.max(40, Math.min(560, p.y)); });
      }
    }
    return pos;
  }

  function applyView(svg) {
    var vp = svg.firstChild;
    if (vp) vp.setAttribute('transform', 'translate(' + state.view.x + ',' + state.view.y + ') scale(' + state.view.k + ')');
  }

  function bindGraphInteractions(svg) {
    if (svg.__osiaBound) return;
    svg.__osiaBound = true;
    svg.addEventListener('wheel', function (ev) {
      ev.preventDefault();
      var f = ev.deltaY < 0 ? 1.1 : 0.9;
      state.view.k = Math.max(0.2, Math.min(4, state.view.k * f));
      applyView(svg);
    }, { passive: false });
    var pan = false, px = 0, py = 0;
    svg.addEventListener('pointerdown', function (ev) {
      if (ev.target && ev.target.closest && ev.target.closest('.node')) { pan = false; return; }
      pan = true; px = ev.clientX; py = ev.clientY;
    });
    svg.addEventListener('pointermove', function (ev) {
      if (!pan) return;
      state.view.x += ev.clientX - px; state.view.y += ev.clientY - py;
      px = ev.clientX; py = ev.clientY;
      applyView(svg);
    });
    svg.addEventListener('pointerup', function () { pan = false; });
    svg.addEventListener('dblclick', function () { state.view = { x: 0, y: 0, k: 1 }; applyView(svg); });
  }

  function renderGraph(svg) {
    var NS = 'http://www.w3.org/2000/svg';
    svg.setAttribute('viewBox', '0 0 800 600');
    var vis = visibleEntities();
    var rels = visibleRelations(vis);
    var pos = computePositions(vis, rels);
    var hidden = state.graph.entities.length - vis.length;
    var counter = $('graph-counter');
    if (counter) counter.textContent = vis.length + ' affichées / ' + state.graph.entities.length + ' au total — ' + hidden + ' masquées par les filtres (masqué ≠ absent, C4-13)';

    var vp = document.createElementNS(NS, 'g');
    vp.setAttribute('id', 'viewport');
    svg.appendChild(vp);
    applyView(svg);

    var edgeEls = {};
    rels.forEach(function (r) {
      var ps = pos[r.src_id], pd = pos[r.dst_id];
      if (!ps || !pd) return;
      var line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', ps.x); line.setAttribute('y1', ps.y);
      line.setAttribute('x2', pd.x); line.setAttribute('y2', pd.y);
      var cls = 'edge';
      if (r.support_level === 'contradictoire') cls += ' contradictoire';
      else if (r.support_level === 'a_confirmer' || r.support_level === 'non_etabli') cls += ' hypothese';
      if (r.human_decision === 'rejected') cls += ' rejected';
      line.setAttribute('class', cls);
      line.setAttribute('tabindex', '0');
      line.setAttribute('role', 'button');
      line.setAttribute('aria-label', 'relation ' + r.type);
      var title = document.createElementNS(NS, 'title');
      title.textContent = r.type + ' — ' + (SUPPORT_LABEL[r.support_level] || r.support_level) + (r.human_decision === 'rejected' ? ' (rejetée)' : '');
      line.appendChild(title);
      line.addEventListener('click', function () { select('relation', r.id); });
      line.addEventListener('keydown', function (e) { if (e.key === 'Enter') select('relation', r.id); });
      vp.appendChild(line);
      edgeEls[r.id] = line;
    });
    function moveEdges(entityId) {
      rels.forEach(function (r) {
        var line = edgeEls[r.id];
        if (!line) return;
        if (r.src_id === entityId) { line.setAttribute('x1', pos[r.src_id].x); line.setAttribute('y1', pos[r.src_id].y); }
        if (r.dst_id === entityId) { line.setAttribute('x2', pos[r.dst_id].x); line.setAttribute('y2', pos[r.dst_id].y); }
      });
    }

    vis.forEach(function (e) {
      var p = pos[e.id];
      var g = document.createElementNS(NS, 'g');
      g.setAttribute('class', 'node' + (state.selected && state.selected.type === 'entity' && state.selected.id === e.id ? ' selected' : ''));
      g.setAttribute('transform', 'translate(' + p.x + ',' + p.y + ')');
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      g.setAttribute('aria-label', 'entité ' + entityLabel(e));
      var c = document.createElementNS(NS, 'circle');
      c.setAttribute('r', '14');
      c.setAttribute('fill', kindColor(e.kind));
      c.setAttribute('fill-opacity', '0.25');
      g.appendChild(c);
      var t = document.createElementNS(NS, 'text');
      t.setAttribute('x', '18'); t.setAttribute('y', '4');
      t.textContent = String(entityLabel(e)).slice(0, 30);
      g.appendChild(t);
      g.addEventListener('click', function () { select('entity', e.id); });
      g.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') select('entity', e.id); });
      var drag = false, sx = 0, sy = 0;
      g.addEventListener('pointerdown', function (ev) { drag = true; sx = ev.clientX; sy = ev.clientY; p.fixed = true; if (g.setPointerCapture) g.setPointerCapture(ev.pointerId); });
      g.addEventListener('pointermove', function (ev) {
        if (!drag) return;
        p.x += (ev.clientX - sx) / state.view.k; p.y += (ev.clientY - sy) / state.view.k;
        sx = ev.clientX; sy = ev.clientY;
        g.setAttribute('transform', 'translate(' + p.x + ',' + p.y + ')');
        moveEdges(e.id);
      });
      g.addEventListener('pointerup', function () { if (drag) { drag = false; savePositions(); } });
      vp.appendChild(g);
    });

    bindGraphInteractions(svg);
  }

  function savePositions() {
    try { storage.setItem('osia_pos_' + state.invId, JSON.stringify(state.positions)); } catch (e) { /* session seulement */ }
  }

  async function select(type, id) {
    state.selected = { type: type, id: id };
    var fiche = $('fiche');
    if (!fiche) return;
    clear(fiche);
    fiche.appendChild(el('h2', { text: type === 'entity' ? 'Entité' : type === 'relation' ? 'Relation' : 'Assertion' }));
    var closeBtn = el('button', { type: 'button', text: 'Fermer' });
    closeBtn.addEventListener('click', function () {
      state.selected = null;
      clear(fiche);
      fiche.appendChild(el('p', { class: 'muted', text: 'Sélectionnez un nœud ou une relation du graphe.' }));
      var s = $('graph-svg'); if (s) { clear(s); renderGraph(s); }
    });
    fiche.appendChild(closeBtn);
    try {
      if (type === 'entity') {
        var sheet = await apiJson('/api/v1/investigations/' + state.invId + '/entities/' + encodeURIComponent(id));
        renderEntitySheet(fiche, sheet);
      } else if (type === 'relation') {
        var r = state.graph.relations.find(function (x) { return x.id === id; });
        if (r) renderRelationSheet(fiche, r);
      } else {
        var a = state.assertions.find(function (x) { return x.id === id; });
        if (a) renderAssertionSheet(fiche, a);
      }
    } catch (e) { if (e.status !== 401) fiche.appendChild(el('p', { class: 'muted', text: e.message })); }
    renderDecisionsHistory(fiche);
  }

  function decisionButtons(fiche, targetType, targetId) {
    var actions = {
      entity: [['annotate', 'Annoter']],
      relation: [['validate', 'Valider'], ['reject', 'Rejeter'], ['annotate', 'Annoter']],
      assertion: [['validate', 'Valider'], ['reject', 'Rejeter'], ['correct', 'Corriger'], ['annotate', 'Annoter']],
      match_proposal: [['validate', 'Valider'], ['reject', 'Rejeter'], ['merge', 'Fusionner'], ['annotate', 'Annoter']]
    }[targetType] || [];
    var row = el('p', { class: 'row' });
    actions.forEach(function (pair) {
      var b = el('button', { type: 'button', text: pair[1] });
      b.addEventListener('click', async function () {
        var payload = {};
        if (pair[0] === 'annotate') { payload.note = window.prompt('Annotation (facultative) :', '') || ''; }
        if (pair[0] === 'correct') {
          var statement = window.prompt('Énoncé corrigé de l’assertion :', '');
          if (!statement || !statement.trim()) return;
          payload.statement = statement.trim();
        }
        try {
          await apiJson('/api/v1/investigations/' + state.invId + '/decisions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target_type: targetType, target_id: targetId, action: pair[0], payload: payload }) });
          await refreshData();
        } catch (e) { if (e.status !== 401) window.alert('Décision refusée : ' + e.message); }
      });
      row.appendChild(b);
    });
    fiche.appendChild(row);
  }

  function renderEntitySheet(fiche, sheet) {
    var e = sheet.entity;
    fiche.appendChild(el('h3', { text: entityLabel(e) }));
    fiche.appendChild(badge(e.kind, ''));
    if (e.merged_into) fiche.appendChild(el('p', { class: 'small muted', text: 'Fusionnée dans ' + e.merged_into }));
    fiche.appendChild(el('h3', { text: 'Identifiants (provenance par attribut)' }));
    var ul = el('ul', { class: 'plain small' });
    (sheet.identifiers || []).forEach(function (i) { ul.appendChild(el('li', { text: (i.kind || '') + ' : ' + (i.value || '') + (i.source_url ? ' — ' + i.source_url : '') })); });
    fiche.appendChild(ul);
    fiche.appendChild(el('h3', { text: 'Relations sortantes' }));
    (sheet.relations_out || []).forEach(function (r) { fiche.appendChild(relationLine(r)); });
    fiche.appendChild(el('h3', { text: 'Relations entrantes' }));
    (sheet.relations_in || []).forEach(function (r) { fiche.appendChild(relationLine(r)); });
    decisionButtons(fiche, 'entity', e.id);
  }
  function relationLine(r) {
    var b = el('button', { type: 'button', class: 'clickable', text: r.type + ' → ' + r.dst_id + ' (' + (SUPPORT_LABEL[r.support_level] || r.support_level) + ')' });
    b.addEventListener('click', function () { select('relation', r.id); });
    return el('p', { class: 'small' }, [b]);
  }
  function renderRelationSheet(fiche, r) {
    fiche.appendChild(el('p', { text: r.src_id + ' → ' + r.dst_id }));
    fiche.appendChild(el('p', {}, [el('strong', { text: 'Type : ' }), document.createTextNode(r.type)]));
    fiche.appendChild(el('p', {}, [badge(SUPPORT_LABEL[r.support_level] || r.support_level, r.support_level), document.createTextNode(' '), badge(HUMAN_LABEL[r.human_decision] || r.human_decision, r.human_decision === 'validated' ? 'validee' : r.human_decision === 'rejected' ? 'rejetee' : 'unexamined')]));
    if (r.valid_from || r.valid_to) fiche.appendChild(el('p', { class: 'small muted', text: 'Temporalité : ' + (r.valid_from || '…') + ' → ' + (r.valid_to || '…') }));
    fiche.appendChild(el('p', { class: 'small', text: 'Preuves : ' + ((r.proof_ids || []).join(', ') || 'aucune') }));
    decisionButtons(fiche, 'relation', r.id);
  }
  function renderAssertionSheet(fiche, a) {
    fiche.appendChild(el('p', { text: a.statement }));
    fiche.appendChild(el('p', {}, [badge(SUPPORT_LABEL[a.support_level] || a.support_level, a.support_level), document.createTextNode(' '), badge(NATURE_LABEL[a.nature] || a.nature, a.nature === 'hypothese' ? 'hypothese' : ''), document.createTextNode(' '), badge(HUMAN_LABEL[a.human_decision] || a.human_decision, a.human_decision === 'validated' ? 'validee' : a.human_decision === 'rejected' ? 'rejetee' : 'unexamined')]));
    if (a.decisive) fiche.appendChild(badge('décisive', 'corrobore'));
    if (a.contradicted_by && a.contradicted_by.length) fiche.appendChild(el('p', { class: 'small', text: 'Contradite par : ' + a.contradicted_by.join(', ') }));
    fiche.appendChild(el('p', { class: 'small', text: 'Preuves : ' + ((a.proof_ids || []).join(', ') || 'aucune') }));
    decisionButtons(fiche, 'assertion', a.id);
  }
  function renderDecisionsHistory(fiche) {
    fiche.appendChild(el('h3', { text: 'Historique des décisions humaines' }));
    var ul = el('ul', { class: 'plain small' });
    var mine = state.decisions.filter(function (d) { return !state.selected || d.target_id === state.selected.id; });
    mine.slice(0, 30).forEach(function (d) {
      var li = el('li', { text: fmtDate(d.created_at) + ' — ' + d.action + ' sur ' + d.target_type + ' ' + d.target_id });
      var undo = el('button', { type: 'button', class: 'clickable small', text: 'annuler' });
      undo.addEventListener('click', async function () {
        try {
          await apiJson('/api/v1/investigations/' + state.invId + '/decisions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target_type: d.target_type, target_id: d.target_id, action: 'undo', reverts: d.id }) });
          await refreshData();
        } catch (e) { if (e.status !== 401) window.alert('Annulation refusée : ' + e.message); }
      });
      li.appendChild(document.createTextNode(' '));
      li.appendChild(undo);
      ul.appendChild(li);
    });
    if (!mine.length) ul.appendChild(el('li', { class: 'muted', text: 'Aucune décision enregistrée.' }));
    fiche.appendChild(ul);
  }

  function renderSynthese(container) {
    if (!container) return;
    clear(container);
    var obj = state.objectif || {};
    var objBox = el('p', {});
    objBox.appendChild(badge(obj.etaye ? 'objectif suffisamment étayé' : 'objectif non encore étayé', obj.etaye ? 'documente' : 'a_confirmer'));
    if (obj.proposition_ia !== undefined && obj.proposition_ia !== null) objBox.appendChild(document.createTextNode(' (proposition IA : ' + (obj.proposition_ia ? 'suffisamment étayé' : 'insuffisant') + ')'));
    container.appendChild(objBox);
    var lastDecisionAt = null;
    state.decisions.forEach(function (d) { if (!lastDecisionAt || d.created_at > lastDecisionAt) lastDecisionAt = d.created_at; });
    if (lastDecisionAt && state.lastObjectiveAt && lastDecisionAt > state.lastObjectiveAt) {
      container.appendChild(el('p', {}, [badge('synthèse à actualiser (décision récente, C3-06)', 'contradictoire')]));
    }
    var list = state.assertions.filter(function (a) { return !a.superseded_by; })
      .sort(function (a, b) { return (b.decisive ? 1 : 0) - (a.decisive ? 1 : 0); });
    if (!list.length) { container.appendChild(el('p', { class: 'muted', text: 'Aucune assertion pour le moment.' })); return; }
    list.forEach(function (a) {
      var div = el('div', { class: 'assertion' });
      var open = el('button', { type: 'button', class: 'clickable', text: a.statement });
      open.addEventListener('click', function () { select('assertion', a.id); });
      div.appendChild(el('p', {}, [open]));
      var badges = el('p', { class: 'badges' });
      badges.appendChild(badge(SUPPORT_LABEL[a.support_level] || a.support_level, a.support_level));
      badges.appendChild(badge(NATURE_LABEL[a.nature] || a.nature, a.nature === 'hypothese' ? 'hypothese' : ''));
      badges.appendChild(badge('humain : ' + (HUMAN_LABEL[a.human_decision] || a.human_decision), a.human_decision === 'validated' ? 'validee' : a.human_decision === 'rejected' ? 'rejetee' : 'unexamined'));
      if (a.decisive) badges.appendChild(badge('décisive', 'corrobore'));
      if (a.contradicted_by && a.contradicted_by.length) badges.appendChild(badge('contradictions conservées', 'contradictoire'));
      div.appendChild(badges);
      if (a.proof_ids && a.proof_ids.length) {
        var pl = el('p', { class: 'small muted' });
        a.proof_ids.forEach(function (pid, i) {
          if (i) pl.appendChild(document.createTextNode(', '));
          var pb = el('button', { type: 'button', class: 'clickable small', text: 'preuve ' + String(pid).slice(0, 12) });
          pb.addEventListener('click', function () { renderProofs(pl, pid); });
          pl.appendChild(pb);
        });
        div.appendChild(pl);
      }
      container.appendChild(div);
    });
  }
  function renderProofs(container, pid) {
    var p = state.proofs.find(function (x) { return x.id === pid || x.sha256 === pid || String(x.sha256 || '').indexOf(pid) === 0; });
    if (p) container.appendChild(el('span', { class: 'small', text: ' — ' + (p.label || '') + ' ' + (p.source_url || '') + ' (' + fmtDate(p.fetched_at) + ')' }));
  }

  function entityLabelById(id) {
    var e = state.graph.entities.find(function (x) { return x.id === id; });
    return e ? entityLabel(e) : id;
  }

  function renderMatches(container) {
    if (!container) return;
    clear(container);
    if (!state.matches.length) {
      container.appendChild(el('p', { class: 'muted small', text: 'Aucune proposition de rapprochement.' }));
      return;
    }
    var ul = el('ul', { class: 'plain' });
    state.matches.forEach(function (m) {
      var li = el('li', { class: 'assertion' });
      li.appendChild(el('p', { class: 'small', text: entityLabelById(m.entity_a) + ' ≈ ' + entityLabelById(m.entity_b) + ' (' + (m.basis || '') + (m.confidence ? ', ' + m.confidence : '') + ')' + (m.justification ? ' — ' + m.justification : '') }));
      if (m.status === 'proposed') {
        decisionButtons(li, 'match_proposal', m.id);
      } else {
        li.appendChild(el('p', { class: 'badges' }, [badge('décision : ' + m.status, m.status === 'validated' ? 'validee' : m.status === 'rejected' ? 'rejetee' : 'unexamined')]));
      }
      ul.appendChild(li);
    });
    container.appendChild(ul);
  }

  function renderRestitution(container) {
    if (!container) return;
    var card = el('div', { class: 'card' });
    var f = el('form', { id: 'export-form' });
    f.appendChild(el('h3', { text: 'Export manuel (jamais automatique, C7-18)' }));
    f.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Format' }), el('select', { name: 'format' }, [el('option', { value: 'osia', text: 'Archive .osia' }), el('option', { value: 'html', text: 'Rapport HTML autonome' }), el('option', { value: 'both', text: 'Les deux' })])]));
    f.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Portée' }), el('select', { name: 'scope' }, [el('option', { value: 'all', text: 'Investigation complète (vue consolidée)' }), el('option', { value: 'branch', text: 'Branche sélectionnée uniquement' })])]));
    f.appendChild(el('label', {}, [el('input', { type: 'checkbox', name: 'include_proofs', checked: 'checked' }), document.createTextNode(' inclure les pièces (preuves)')]));
    var excl = el('fieldset', {});
    excl.appendChild(el('legend', { text: 'Exclusions (T7.4) — le périmètre réel figure dans le manifeste' }));
    ['proofs', 'tasks', 'external_ops', 'reservations', 'ledger', 'events'].forEach(function (x) {
      excl.appendChild(el('label', {}, [el('input', { type: 'checkbox', name: 'excl', value: x }), document.createTextNode(' exclure ' + x)]));
    });
    f.appendChild(excl);
    f.appendChild(el('label', {}, [el('input', { type: 'checkbox', name: 'encrypt' }), document.createTextNode(' chiffrer (AES-256-GCM, CON-15)')]));
    f.appendChild(el('label', { class: 'field' }, [el('span', { text: 'Phrase de chiffrement (si cochée ; jamais journalisée)' }), el('input', { type: 'password', name: 'passphrase', autocomplete: 'off' })]));
    f.appendChild(el('button', { type: 'submit', class: 'primary', text: 'Exporter' }));
    f.appendChild(el('span', { id: 'export-result', class: 'small muted' }));
    card.appendChild(f);

    f.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      var fd = new FormData(f);
      var body = {
        format: String(fd.get('format')),
        include_proofs: fd.get('include_proofs') === 'on',
        exclusions: fd.getAll('excl'),
        encrypt: fd.get('encrypt') === 'on',
        passphrase: fd.get('encrypt') === 'on' ? String(fd.get('passphrase') || '') : null
      };
      if (String(fd.get('scope')) === 'branch' && state.branchFilter) body.branch_ids = [state.branchFilter];
      if (String(fd.get('scope')) === 'branch' && !state.branchFilter) {
        var w = $('export-result');
        if (w) w.textContent = 'Portée « branche » sélectionnée mais aucune branche active : sélectionnez une branche dans l’arbre, ou choisissez la portée consolidée.';
        return;
      }
      try {
        var res = await apiJson('/api/v1/investigations/' + state.invId + '/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        var out = $('export-result');
        if (!out) return;
        clear(out);
        out.appendChild(document.createTextNode(' export ' + res.export_id + ' (' + res.format + (res.partial ? ', partiel' : '') + (res.warnings && res.warnings.length ? ', avertissements : ' + res.warnings.join(' ; ') : '') + ') — '));
        (res.files || []).forEach(function (file, i) {
          if (i) out.appendChild(document.createTextNode(', '));
          var a = el('button', { type: 'button', class: 'clickable small', text: 'télécharger ' + file.file });
          a.addEventListener('click', function () { downloadExport(res.export_id, file.file); });
          out.appendChild(a);
        });
      } catch (e) { if (e.status !== 401) window.alert('Export refusé : ' + e.message); }
    });

    var imp = el('details', {});
    imp.appendChild(el('summary', { text: 'Import supervisé d’une archive .osia (T7.6)' }));
    var fi = el('input', { type: 'file', accept: '.osia,application/zip', id: 'import-file' });
    imp.appendChild(fi);
    var prevBtn = el('button', { type: 'button', text: 'Prévisualiser' });
    var applyAdd = el('button', { type: 'button', text: 'Appliquer (ajout)' });
    var applyMerge = el('button', { type: 'button', text: 'Appliquer (fusion)' });
    var prevBox = el('pre', { class: 'small', id: 'import-preview' });
    imp.appendChild(el('p', { class: 'row' }, [prevBtn, applyAdd, applyMerge]));
    imp.appendChild(prevBox);
    var currentFile = null;
    fi.addEventListener('change', function () { currentFile = fi.files && fi.files[0] ? fi.files[0] : null; });
    prevBtn.addEventListener('click', async function () {
      if (!currentFile) return;
      try {
        var r = await api('/api/v1/import/preview', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: currentFile });
        prevBox.textContent = JSON.stringify(await r.json(), null, 2).slice(0, 4000);
      } catch (e) { if (e.status !== 401) prevBox.textContent = 'Prévisualisation refusée : ' + e.message; }
    });
    async function apply(mode) {
      if (!currentFile) return;
      try {
        var r = await api('/api/v1/import/apply?mode=' + mode + '&on_conflict=fail', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: currentFile });
        if (r.status === 409) { prevBox.textContent = 'Conflits détectés (aucun écrasement silencieux) : ' + JSON.stringify((await r.json()).error.details); return; }
        prevBox.textContent = 'Import appliqué (' + mode + ') : ' + JSON.stringify(await r.json()).slice(0, 2000);
      } catch (e) { if (e.status !== 401) prevBox.textContent = 'Import refusé : ' + e.message; }
    }
    applyAdd.addEventListener('click', function () { apply('add'); });
    applyMerge.addEventListener('click', function () { apply('merge'); });
    card.appendChild(imp);

    var backups = el('details', {});
    backups.appendChild(el('summary', { text: 'Sauvegardes techniques manuelles (T2.6, distinctes de l’export)' }));
    var bkBtn = el('button', { type: 'button', text: 'Créer une sauvegarde à chaud' });
    var bkList = el('ul', { class: 'plain small', id: 'backup-list' });
    backups.appendChild(bkBtn); backups.appendChild(bkList);
    bkBtn.addEventListener('click', async function () {
      try {
        await apiJson('/api/v1/backups', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        await renderBackups(bkList);
      } catch (e) { if (e.status !== 401) window.alert('Sauvegarde refusée : ' + e.message); }
    });
    renderBackups(bkList);
    card.appendChild(backups);
    container.appendChild(card);
  }

  async function renderBackups(ul) {
    if (!ul) return;
    clear(ul);
    try {
      var list = await apiJson('/api/v1/backups');
      list.forEach(function (b) {
        var li = el('li', {});
        li.appendChild(document.createTextNode(b.id + ' — ' + fmtDate(b.created_at) + ' — ' + b.size_bytes + ' octets '));
        var v = el('button', { type: 'button', class: 'clickable small', text: 'vérifier' });
        v.addEventListener('click', async function () {
          try {
            var r = await apiJson('/api/v1/backups/' + encodeURIComponent(b.id) + '/verify', { method: 'POST' });
            li.appendChild(document.createTextNode(' vérifiée : ' + JSON.stringify(r.verify_errors || 'ok')));
          } catch (e) { if (e.status !== 401) li.appendChild(document.createTextNode(' ' + e.message)); }
        });
        li.appendChild(v);
        ul.appendChild(li);
      });
      if (!list.length) ul.appendChild(el('li', { class: 'muted', text: 'Aucune sauvegarde.' }));
    } catch (e) { if (e.status !== 401) ul.appendChild(el('li', { class: 'muted', text: e.message })); }
  }

  async function downloadExport(exportId, file) {
    try {
      var r = await api('/api/v1/exports/' + encodeURIComponent(exportId) + '/download?file=' + encodeURIComponent(file));
      if (!r.ok) throw new Error('HTTP ' + r.status);
      var blob = await r.blob();
      var url = URL.createObjectURL(blob);
      var a = el('a', { href: url, download: file });
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    } catch (e) { if (e.status !== 401) window.alert('Téléchargement impossible : ' + e.message); }
  }

  async function startEvents(invId) {
    var ctrl = new AbortController();
    state.sseAbort = ctrl;
    var cursor = state.cursor;
    var base = '/api/v1/investigations/' + encodeURIComponent(invId) + '/events?last_event_id=';
    while (!ctrl.signal.aborted) {
      try {
        var resp = await fetch(base + cursor, { headers: Object.assign({ Accept: 'text/event-stream' }, authHeaders()), signal: ctrl.signal });
        if (resp.status === 401) { showAuth(); return; }
        if (!resp.body) { await sleep(2000); continue; }
        var reader = resp.body.getReader();
        var dec = new TextDecoder();
        var buf = '';
        while (true) {
          var chunk = await reader.read();
          if (chunk.done) break;
          buf += dec.decode(chunk.value, { stream: true });
          var idx;
          while ((idx = buf.indexOf('\n\n')) >= 0) {
            var block = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            var m = block.match(/^id: (\d+)/m);
            if (m) cursor = Math.max(cursor, Number(m[1]));
            handleSseBlock(block);
          }
        }
      } catch (e) {
        if (ctrl.signal.aborted) return;
        await sleep(2000);
      }
    }
  }
  function handleSseBlock(block) {
    if (block.indexOf(':') === 0) return;
    var id = 0, type = 'message', data = '';
    block.split('\n').forEach(function (line) {
      if (line.indexOf('id:') === 0) id = Number(line.slice(3).trim());
      else if (line.indexOf('event:') === 0) type = line.slice(6).trim();
      else if (line.indexOf('data:') === 0) data += line.slice(5).trim();
    });
    if (!id) return;
    state.cursor = Math.max(state.cursor, id);
    var ev = { id: id, type: type, payload: {}, created_at: null };
    try { var parsed = data ? JSON.parse(data) : {}; ev.payload = parsed.payload || {}; ev.created_at = parsed.created_at || null; } catch (e) { /* bloc partiel */ }
    appendJournal(ev);
    onEvent(ev);
  }
  function appendJournal(ev, replay) {
    if (!replay) {
      state.journal.push(ev);
      if (state.journal.length > 300) state.journal = state.journal.slice(-300);
    }
    var ul = $('journal');
    if (!ul) return;
    var li = el('li', {});
    li.appendChild(el('span', { class: 'evt-type', text: ev.type }));
    var detail = ev.payload && (ev.payload.query || ev.payload.error || ev.payload.url) ? (ev.payload.query || ev.payload.error || ev.payload.url) : '';
    if (detail) li.appendChild(document.createTextNode(' ' + detail));
    ul.appendChild(li);
    while (ul.children.length > 300) ul.removeChild(ul.firstChild);
  }
  function onEvent(ev) {
    if (ev.type === 'objective.evalue') state.lastObjectiveAt = ev.created_at || new Date().toISOString();
    if (state.refreshTimer) clearTimeout(state.refreshTimer);
    state.refreshTimer = setTimeout(function () { refreshData(); }, 600);
  }
  async function refreshData() {
    if (!state.invId) return;
    try { await loadInvestigationData(state.invId); } catch (e) { if (e.status === 401) return; }
    if (!$('layout')) return;
    renderLayout();
    if (state.selected) select(state.selected.type, state.selected.id);
  }

  async function boot() {
    bindAuth();
    window.addEventListener('hashchange', renderRoute);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var f = $('fiche');
        if (f && state.selected) {
          state.selected = null;
          clear(f);
          f.appendChild(el('p', { class: 'muted', text: 'Sélectionnez un nœud ou une relation du graphe.' }));
        }
      }
    });
    await init();
  }
  window.OSIA = { state: state, init: init, renderRoute: renderRoute, el: el, renderHome: renderHome };
  if (typeof document !== 'undefined' && document.getElementById) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
  }
})();
