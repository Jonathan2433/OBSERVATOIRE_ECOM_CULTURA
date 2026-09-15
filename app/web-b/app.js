/* =====================================================================
   OBSERVATOIRE ECOM STUDIO — Direction B · application (vanilla, API-driven)
   ---------------------------------------------------------------------
   Reprend le rendu validé de la maquette Direction B et le branche sur
   l'API FastAPI réelle via window.API (cf. api.js). Aucune dépendance,
   compatible CSP stricte (pas de script inline, ressources same-origin).
   ===================================================================== */
(function () {
  'use strict';

  var MONO = "'JetBrains Mono','SF Mono',ui-monospace,Menlo,Consolas,monospace";
  var root = document.getElementById('approot');
  var API = window.API;

  var SIG = {
    RUP: { l: 'Rupture client', c: 'RUP', bg: '#fef3f2', fg: '#b42318' },
    CHU: { l: 'Churn', c: 'CHU', bg: '#fffaeb', fg: '#b54708' },
    INS: { l: 'Insatisfaction forte', c: 'INS', bg: '#fce7f0', fg: '#c01573' }
  };
  var STATUS_MAP = { pending: 'attente', running: 'encours', done: 'termine', failed: 'echec', canceled: 'annule' };
  var SENT_MAP = { 'Négatif': 'neg', 'Neutre': 'neu', 'Positif': 'pos' };
  var SENT_REV = { neg: 'Négatif', neu: 'Neutre', pos: 'Positif' };
  var KIND_LABEL = { real: 'Modèle entraîné', stub: 'Heuristique', lmstudio: 'LLM local' };

  /* ================================================================ ÉTAT */
  var state = {
    booting: true, authed: false, me: null,
    route: 'accueil', loginId: '', loginPw: '', loginError: '', loginBusy: false,
    meta: null, modelKpi: null, taxonomy: null,
    batches: null, volumetry: null,
    detailBatch: null, detailObj: null, detailTab: 'dashboard', detailKpi: null, detailLoading: false,
    results: null, resultsLoading: false, resultsOffset: 0,
    fSent: '', fStatus: '', fSignal: '', fText: '', fTheme: '',
    reviewQueue: null, revIdx: 0, revForm: null,
    users: null, audit: null, models: null, config: null, ops: null,
    adminTab: 'config', cfgRetention: 12, cfgSeuil: 0.5,
    testText: '', testNote: '', testRes: null, testLoading: false,
    pwOld: '', pwNew: '', pwConf: '', pwMsg: '',
    nbLabel: '', nbSeuil: 0.5, nbMDTC: null, nbMopinion: null, nbRunning: false, nbProgress: 0, nbDone: false, nbError: '', nbBatchId: null,
    toast: '', error: ''
  };
  var toastTimer = null, pollTimer = null, testTimer = null, filterTimer = null;

  /* ================================================================ FORMAT */
  function fmt(n) { return Number(n || 0).toLocaleString('fr-FR'); }
  function dec(n) { return Number(n || 0).toFixed(2).replace('.', ','); }
  function pct1(n) { return Number(n).toFixed(1).replace('.', ',') + ' %'; }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function fmtDate(iso) { if (!iso) return '—'; var d = new Date(iso); if (isNaN(d.getTime())) return '—'; var p = function (n) { return (n < 10 ? '0' : '') + n; }; return p(d.getDate()) + '/' + p(d.getMonth() + 1) + '/' + d.getFullYear(); }
  function fmtDuration(s) { if (s == null) return '—'; s = Math.round(s); var m = Math.floor(s / 60), r = s % 60; return m + 'm ' + (r < 10 ? '0' : '') + r + 's'; }
  function humanSize(bytes) { if (!bytes && bytes !== 0) return ''; var mo = bytes / (1024 * 1024); return mo >= 1 ? mo.toFixed(1).replace('.', ',') + ' Mo' : Math.max(1, Math.round(bytes / 1024)) + ' Ko'; }
  function go1(bytes) { return (bytes / 1e9).toFixed(1).replace('.', ','); }

  function sentKey(s) { return SENT_MAP[s] || 'neu'; }
  function sigArr(r) { var a = []; if (r.signal_rupture) a.push('RUP'); if (r.signal_churn) a.push('CHU'); if (r.signal_insatisfaction) a.push('INS'); return a; }
  function mapBatch(b) {
    return {
      id: String(b.id), label: b.label || ('lot-' + b.id), status: STATUS_MAP[b.status] || 'attente',
      progress: b.status === 'done' ? 100 : (b.n_total ? Math.round(b.n_processed / b.n_total * 100) : 0),
      count: b.n_total || 0, reviewPct: b.n_total ? (b.n_review / b.n_total * 100) : 0,
      engine: b.model_label || (state.meta && state.meta.active_model && state.meta.active_model.label) || '—', date: fmtDate(b.created_at)
    };
  }
  function mapResult(r) {
    return {
      id: r.id, src: r.source || '', text: r.verbatim_analyse || '', t1: r.theme1_niv1 || '', t2: r.theme1_niv2 || '',
      sent: sentKey(r.theme1_sentiment), sig: sigArr(r), conf: r.confidence_globale == null ? 0 : r.confidence_globale,
      status: r.corrected ? 'corrige' : (r.revue_requise ? 'revue' : 'auto'),
      tc1: r.theme1_score == null ? (r.confidence_globale || 0) : r.theme1_score, tc2: r.theme2_score == null ? 0 : r.theme2_score
    };
  }
  function themesMap() {
    var t = {}; ((state.taxonomy && state.taxonomy.themes) || []).forEach(function (x) { t[x.niv1] = x.niv2 || []; }); return t;
  }

  /* ================================================================ ATOMES */
  function attrs(o) { return Object.keys(o).map(function (k) { return k + '="' + o[k] + '"'; }).join(' '); }
  function ic(name, o) {
    o = o || {}; var s = o.size || 18, col = o.color || 'currentColor', st = o.stroke || 2;
    var P = {
      home: ['M3 9.5 12 3l9 6.5V21H3z'], layers: ['m12 2 9 5-9 5-9-5 9-5z', 'm3 12 9 5 9-5', 'm3 17 9 5 9-5'],
      chart: ['M12 20V10', 'M18 20V4', 'M6 20v-6'], flask: ['M9 3h6', 'M10 3v6l-4 9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1l-4-9V3'],
      help: ['M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4', 'M12 17h.01'], users: ['M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M22 21v-2a4 4 0 0 0-3-3.9', 'M16 3.1a4 4 0 0 1 0 7.7'],
      grid: ['M3 9h18', 'M9 21V9'], upload: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'M17 8l-5-5-5 5', 'M12 3v12'],
      check: ['M20 6 9 17l-5-5'], doc: ['M14 2v6h6'], play: ['M5 3v18l15-9L5 3z']
    };
    var extra = { help: [['circle', { cx: 12, cy: 12, r: 9 }]], users: [['circle', { cx: 9, cy: 7, r: 4 }]], doc: [['path', { d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' }]], grid: [['rect', { x: 3, y: 3, width: 18, height: 18, rx: 2 }]] };
    var inner = '';
    (extra[name] || []).forEach(function (e) { inner += '<' + e[0] + ' ' + attrs(e[1]) + '></' + e[0] + '>'; });
    (P[name] || ['M12 2v0']).forEach(function (d) { inner += '<path d="' + d + '"></path>'; });
    var fill = name === 'play' ? col : 'none';
    return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="' + fill + '" stroke="' + col + '" stroke-width="' + st + '" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;">' + inner + '</svg>';
  }
  function tag(text, bg, fg, o) {
    o = o || {};
    var pad = o.pill ? '2px 9px' : '1px 7px', radius = o.pill ? '9999px' : '4px', fs = o.fs || 11, fw = o.fw || 600;
    var border = o.bd ? ('1px solid ' + o.bd) : 'none', ff = o.mono ? MONO : 'inherit', title = o.title ? ' title="' + esc(o.title) + '"' : '';
    var dot = o.dot ? '<span style="width:6px;height:6px;border-radius:50%;background:currentColor;"></span>' : '';
    return '<span' + title + ' style="display:inline-flex;align-items:center;gap:5px;background:' + bg + ';color:' + fg + ';padding:' + pad + ';border-radius:' + radius + ';font-size:' + fs + 'px;font-weight:' + fw + ';line-height:16px;white-space:nowrap;border:' + border + ';font-family:' + ff + ';' + (o.style || '') + '">' + dot + esc(text) + '</span>';
  }
  function anonText(t) {
    return String(t == null ? '' : t).split(/(\[[A-Z]+\])/g).map(function (p) {
      if (/^\[[A-Z]+\]$/.test(p)) return '<span style="font-family:' + MONO + ';font-size:0.84em;color:#6941c6;background:#f4ebff;padding:0 4px;border-radius:4px;">' + esc(p) + '</span>';
      return esc(p);
    }).join('');
  }
  function sentEl(s) { var m = { neg: ['NÉG', '#fef3f2', '#b42318'], neu: ['NEU', '#f2f4f7', '#344054'], pos: ['POS', '#ecfdf3', '#067647'] }[s]; return tag(m[0], m[1], m[2]); }
  function sentFull(s) { var m = { neg: ['Négatif', '#fef3f2', '#b42318'], neu: ['Neutre', '#f2f4f7', '#344054'], pos: ['Positif', '#ecfdf3', '#067647'] }[s]; return tag(m[0], m[1], m[2], { pill: true, dot: true, fs: 12, fw: 500 }); }
  function sigEls(arr) {
    if (!arr || !arr.length) return '<span style="color:#98a2b3;font-size:11px;">—</span>';
    return '<span style="display:inline-flex;gap:3px;">' + arr.map(function (c) { var s = SIG[c]; return tag(s.c, s.bg, s.fg, { mono: true, fs: 10, title: s.l }); }).join('') + '</span>';
  }
  function statusVerb(st) {
    if (st === 'auto') return '<span style="font-size:11px;color:#667085;">auto</span>';
    if (st === 'revue') return tag('à revoir', '#fffaeb', '#b54708', { fs: 10, fw: 600, style: 'padding:1px 6px;' });
    return tag('corrigé', '#f9f5ff', '#6941c6', { fs: 10, fw: 600, style: 'padding:1px 6px;' });
  }
  function confEl(c) {
    var col = c >= 0.8 ? '#079455' : (c < 0.5 ? '#dc6803' : '#475467'); var fill = c >= 0.8 ? '#17b26a' : (c < 0.5 ? '#f79009' : '#98a2b3');
    return '<span style="display:inline-flex;align-items:center;gap:7px;width:100%;"><span style="flex:1;height:5px;background:#e4e7ec;border-radius:9999px;overflow:hidden;"><span style="display:block;width:' + (c * 100) + '%;height:100%;background:' + fill + ';border-radius:9999px;"></span></span><span style="font-family:' + MONO + ';font-size:11px;color:' + col + ';font-weight:600;width:30px;">' + dec(c) + '</span></span>';
  }
  function batchStatusEl(st) {
    var m = { termine: ['Terminé', '#ecfdf3', '#067647'], encours: ['En cours', '#eef4ff', '#3538cd'], attente: ['En attente', '#f2f4f7', '#475467'], echec: ['Échec', '#fef3f2', '#b42318'], annule: ['Annulé', '#f9fafb', '#98a2b3'] }[st] || ['—', '#f2f4f7', '#475467'];
    var sz = st === 'encours' ? '7px' : '6px', an = st === 'encours' ? 'animation:pulse 1.2s infinite;' : '';
    return '<span style="display:inline-flex;align-items:center;gap:6px;background:' + m[1] + ';color:' + m[2] + ';padding:2px 9px;border-radius:4px;font-size:11px;font-weight:600;"><span style="width:' + sz + ';height:' + sz + ';border-radius:50%;background:currentColor;' + an + '"></span>' + m[0] + '</span>';
  }
  function progEl(p, st) {
    if (st === 'attente') return '<span style="font-size:11px;color:#98a2b3;">—</span>';
    var col = st === 'echec' ? '#f04438' : (st === 'annule' ? '#98a2b3' : '#7f56d9');
    return '<span style="display:inline-flex;align-items:center;gap:8px;width:100%;"><span style="flex:1;height:6px;background:#e4e7ec;border-radius:9999px;overflow:hidden;"><span style="display:block;width:' + p + '%;height:100%;background:' + col + ';border-radius:9999px;"></span></span><span style="font-family:' + MONO + ';font-size:11px;color:#475467;width:34px;text-align:right;">' + p + ' %</span></span>';
  }
  function tabSt(a) { return 'padding:10px 14px;font-size:14px;font-weight:' + (a ? 600 : 500) + ';cursor:pointer;color:' + (a ? '#6941c6' : '#667085') + ';border-bottom:' + (a ? '2px solid #7f56d9' : '2px solid transparent') + ';margin-bottom:-1px;display:inline-flex;align-items:center;gap:7px;'; }
  function seg(active, col, bg) { return 'padding:8px 14px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:1px solid ' + (active ? col : '#d0d5dd') + ';background:' + (active ? bg : '#fff') + ';color:' + (active ? col : '#475467') + ';'; }
  function options(list, current) { return list.map(function (o) { return '<option value="' + esc(o[0]) + '"' + (String(o[0]) === String(current) ? ' selected' : '') + '>' + esc(o[1]) + '</option>'; }).join(''); }
  function inits(n) { return String(n || '').split(/[ .]/).filter(Boolean).map(function (w) { return w[0]; }).join('').slice(0, 2).toUpperCase() || '?'; }
  function loadingPanel(label) {
    return '<div style="display:flex;align-items:center;gap:10px;padding:40px 16px;color:var(--text-quaternary);font-size:13px;"><span style="width:16px;height:16px;border:2px solid #e4e7ec;border-top-color:#7f56d9;border-radius:50%;animation:spin .7s linear infinite;display:inline-block;"></span>' + (label || 'Chargement…') + '</div>';
  }
  function errorPanel(msg) {
    return '<div style="border:1px solid #fecdca;background:#fffbfa;border-radius:8px;padding:16px;color:var(--error-700);font-size:13.5px;display:flex;align-items:center;gap:9px;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>' + esc(msg) + '</div>';
  }

  /* ================================================================ LOGIN */
  function loginScreen() {
    var err = state.loginError ? '<div style="display:flex;align-items:center;gap:8px;background:var(--error-50);border:1px solid #fecdca;color:var(--error-700);font-size:13px;padding:9px 12px;border-radius:8px;margin-bottom:16px;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg><span>' + esc(state.loginError) + '</span></div>' : '';
    var btnLabel = state.loginBusy ? 'Connexion…' : 'Se connecter';
    return '<div style="height:100vh;display:flex;align-items:center;justify-content:center;background:var(--gray-50);position:relative;">' +
      '<div style="position:absolute;inset:0;background:radial-gradient(900px 500px at 50% -10%, #f4ebff 0%, transparent 60%);"></div>' +
      '<div style="position:relative;width:404px;background:#fff;border:1px solid var(--border-secondary);border-radius:12px;box-shadow:var(--shadow-lg);padding:34px 32px;">' +
        '<div style="display:flex;align-items:center;gap:11px;margin-bottom:26px;"><div style="width:38px;height:38px;border-radius:9px;background:var(--brand-600);display:grid;place-items:center;"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 5-6"/></svg></div><div style="line-height:1.15;"><div style="font-size:16px;font-weight:600;">Observatoire Ecom Studio</div><div style="font-size:12px;color:var(--text-quaternary);">Classification des verbatims · groupe Cultura</div></div></div>' +
        '<div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Identifiant</div>' +
        '<input data-f="loginId" data-input="loginId" value="' + esc(state.loginId) + '" placeholder="prenom.nom" style="width:100%;height:42px;padding:0 12px;border:1px solid var(--border-primary);border-radius:8px;font-size:14px;margin-bottom:16px;box-shadow:var(--shadow-xs);" />' +
        '<div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Mot de passe</div>' +
        '<input data-f="loginPw" data-input="loginPw" data-keydown="loginKey" value="' + esc(state.loginPw) + '" type="password" placeholder="••••••••" style="width:100%;height:42px;padding:0 12px;border:1px solid var(--border-primary);border-radius:8px;font-size:14px;margin-bottom:18px;box-shadow:var(--shadow-xs);" />' +
        err +
        '<button data-click="doLogin" class="h-brand" style="width:100%;height:44px;background:var(--brand-600);color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;box-shadow:var(--shadow-xs);' + (state.loginBusy ? 'opacity:.7;' : '') + '">' + btnLabel + '</button>' +
        '<div style="margin-top:18px;display:flex;align-items:center;gap:7px;font-size:12px;color:var(--text-quaternary);justify-content:center;"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>Outil interne · 100 % local et hors-ligne · aucune donnée envoyée</div>' +
      '</div></div>';
  }

  /* ================================================================ COQUILLE */
  function isAdmin() { return state.me && state.me.role === 'admin'; }
  function navHTML() {
    var r = state.route;
    var main = [['accueil', 'Accueil', 'home'], ['lots', 'Lots', 'layers'], ['dashboards', 'Tableaux de bord', 'chart'], ['test', 'Test à la volée', 'flask'], ['help', 'Comment ça marche', 'help']];
    var adm = [['users', 'Utilisateurs', 'users'], ['admin', 'Administration', 'grid']];
    function item(it) {
      var active = (it[0] === r) || (it[0] === 'lots' && r === 'detail');
      var st = 'display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:8px;font-size:13.5px;font-weight:500;cursor:pointer;margin-bottom:1px;color:' + (active ? '#fff' : '#cfd2d8') + ';background:' + (active ? 'rgba(127,86,217,.24)' : 'transparent') + ';box-shadow:' + (active ? 'inset 2px 0 0 #b692f6' : 'none') + ';';
      return '<div data-click="go" data-arg="' + it[0] + '" style="' + st + '">' + ic(it[2], { size: 18, color: active ? '#fff' : '#cfd2d8' }) + '<span>' + it[1] + '</span></div>';
    }
    return { main: main.map(item).join(''), adm: adm.map(item).join('') };
  }
  function aside() {
    var nav = navHTML();
    var uname = (state.me && state.me.username) || '—';
    var role = state.me && state.me.role === 'admin' ? 'Admin' : 'Analyste';
    var adminGroup = isAdmin() ? ('<div style="height:1px;background:rgba(255,255,255,.08);margin:12px 8px;"></div>' +
      '<div style="font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--gray-500);padding:0 8px 6px;">Administration</div>' + nav.adm) : '';
    return '<aside style="width:222px;flex:none;background:var(--gray-900);display:flex;flex-direction:column;padding:14px 10px;">' +
      '<div style="display:flex;align-items:center;gap:10px;padding:6px 8px 16px;"><div style="width:32px;height:32px;border-radius:8px;background:var(--brand-600);display:grid;place-items:center;flex:none;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 5-6"/></svg></div><div style="line-height:1.15;"><div style="font-size:13.5px;font-weight:600;color:#fff;">Observatoire</div><div style="font-size:10.5px;font-weight:500;color:var(--gray-400);">Ecom Studio</div></div></div>' +
      nav.main + adminGroup +
      '<div data-click="account" class="h-acct" style="margin-top:auto;display:flex;align-items:center;gap:9px;padding:9px 8px;border-top:1px solid rgba(255,255,255,.08);cursor:pointer;border-radius:8px;">' +
        '<div style="width:32px;height:32px;border-radius:50%;background:var(--brand-700);color:#fff;display:grid;place-items:center;font-size:12px;font-weight:600;flex:none;">' + inits(uname) + '</div>' +
        '<div style="line-height:1.2;min-width:0;"><div style="font-size:12.5px;font-weight:600;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(uname) + '</div><div style="font-size:10.5px;color:var(--gray-400);">' + role + '</div></div>' +
        '<div data-click="logout" class="h-logout" title="Se déconnecter" style="margin-left:auto;color:var(--gray-400);display:grid;place-items:center;padding:4px;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/></svg></div>' +
      '</div></aside>';
  }
  function topbar() {
    var titles = { accueil: 'Accueil', lots: 'Lots', detail: 'Détail du lot', dashboards: 'Tableaux de bord', test: 'Test à la volée', help: 'Comment ça marche', users: 'Utilisateurs', admin: 'Administration', account: 'Mon compte' };
    var engine = (state.meta && state.meta.active_model && state.meta.active_model.label) || '—';
    return '<header style="height:56px;flex:none;background:#fff;border-bottom:1px solid var(--border-secondary);display:flex;align-items:center;padding:0 24px;gap:16px;">' +
      '<div style="font-size:15px;font-weight:600;color:var(--text-primary);">' + esc(titles[state.route] || '') + '</div>' +
      '<div style="margin-left:auto;display:flex;align-items:center;gap:14px;"><div style="display:flex;align-items:center;gap:8px;padding:5px 11px;border:1px solid var(--border-secondary);border-radius:8px;background:var(--gray-25);font-size:12.5px;"><span style="width:7px;height:7px;border-radius:50%;background:var(--success-500);"></span><span style="color:var(--text-quaternary);">Moteur actif</span><span style="font-weight:600;color:var(--text-secondary);font-family:' + MONO + ';">' + esc(engine) + '</span></div>' +
      '<button data-click="go" data-arg="new" class="h-brand" style="display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 14px;background:var(--brand-600);color:#fff;border:none;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;box-shadow:var(--shadow-xs);"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>Nouveau lot</button></div></header>';
  }
  function toast() {
    if (!state.toast) return '';
    return '<div style="position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:50;display:flex;align-items:center;gap:9px;background:var(--gray-900);color:#fff;padding:11px 16px;border-radius:9px;box-shadow:var(--shadow-lg);font-size:13.5px;font-weight:500;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6ce9a6" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>' + esc(state.toast) + '</div>';
  }

  /* ================================================================ ACCUEIL */
  function home() {
    if (!state.batches || !state.volumetry) return wrap(loadingPanel('Chargement du tableau de bord…'));
    var batches = state.batches, vol = state.volumetry, mk = state.modelKpi && state.modelKpi.active;
    // « ce mois » = mois du lot le plus récent (stable, indépendant de l'horloge)
    var latest = batches.reduce(function (acc, b) { var d = b.created_at ? new Date(b.created_at) : null; return (d && (!acc || d > acc)) ? d : acc; }, null);
    var mkey = latest ? (latest.getFullYear() + '-' + latest.getMonth()) : null;
    var inMonth = batches.filter(function (b) { if (!mkey || !b.created_at) return false; var d = new Date(b.created_at); return (d.getFullYear() + '-' + d.getMonth()) === mkey; });
    var nDone = inMonth.filter(function (b) { return b.status === 'done'; }).length;
    var nRun = inMonth.filter(function (b) { return b.status === 'running'; }).length;
    var totReview = (vol.series || []).reduce(function (a, s) { return a + s.n_review; }, 0);
    var totVerb = (vol.series || []).reduce(function (a, s) { return a + s.n_total; }, 0);
    var seuil = state.meta ? dec(state.meta.default_seuil_revue) : '0,50';
    var f1n1 = mk && mk.metrics && mk.metrics.f1_macro_niv1 != null ? dec(mk.metrics.f1_macro_niv1) : '—';

    var box = 'padding:13px 16px;border-right:1px solid #e4e7ec;', boxL = 'padding:13px 16px;';
    var kpis = [
      ['Lots ce mois', String(inMonth.length), nDone + ' terminés · ' + nRun + ' en cours', '#101828', box],
      ['Verbatims traités', fmt(vol.total_verbatims || totVerb), 'sur ' + (vol.n_batches || 0) + ' lots terminés', '#101828', box],
      ['En revue', totVerb ? pct1(totReview / totVerb * 100) : '—', 'sous le seuil ' + seuil, '#b54708', box],
      ['F1 modèle niv.1', f1n1, 'cible 0,80', '#101828', boxL]
    ].map(function (k) {
      return '<div style="' + k[4] + '"><div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:7px;">' + k[0] + '</div><div style="font-size:23px;font-weight:600;font-family:' + MONO + ';color:' + k[3] + ';">' + k[1] + '</div><div style="font-size:11.5px;color:var(--text-quaternary);margin-top:3px;">' + k[2] + '</div></div>';
    }).join('');

    var recent = batches.slice(0, 4).map(mapBatch).map(function (b) {
      return '<div data-click="openBatch" data-arg="' + b.id + '" class="h-row" style="display:flex;align-items:center;gap:16px;padding:12px 16px;border-bottom:1px solid var(--border-tertiary);cursor:pointer;"><div style="flex:1;min-width:0;"><div style="font-size:13.5px;font-weight:500;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(b.label) + '</div><div style="font-size:11.5px;color:var(--text-quaternary);font-family:' + MONO + ';">#' + b.id + ' · ' + (b.count > 0 ? fmt(b.count) : '—') + ' verbatims</div></div><div style="width:140px;flex:none;display:flex;flex-direction:column;gap:7px;align-items:flex-start;"><div>' + batchStatusEl(b.status) + '</div><div style="width:100%;">' + progEl(b.progress, b.status) + '</div></div></div>';
    }).join('') || '<div style="padding:18px 16px;color:var(--text-quaternary);font-size:13px;">Aucun lot.</div>';

    var avail = mk ? (mk.available ? tag('Disponible', '#ecfdf3', '#067647', { pill: true, dot: true, fs: 12, fw: 600, style: 'border:1px solid #abefc6;' }) : tag('Indisponible', '#fef3f2', '#b42318', { pill: true, dot: true, fs: 12, fw: 600 })) : '';
    var mName = mk ? mk.label : '—', mKind = mk ? (KIND_LABEL[mk.kind] || mk.kind) : '';
    var m = (mk && mk.metrics) || {};
    function f1row(label, v, warn) { var val = v == null ? '—' : dec(v); var c = warn && v != null && v < 0.7 ? 'color:var(--warning-700);' : ''; return '<div style="display:flex;justify-content:space-between;font-size:12.5px;padding:7px 0;border-top:1px solid var(--border-tertiary);"><span style="color:var(--text-tertiary);">' + label + '</span><span style="font-family:' + MONO + ';font-weight:600;' + c + '">' + val + (warn && v != null && v < 0.7 ? ' ⚠' : '') + '</span></div>'; }

    return '<div style="max-width:1180px;">' +
      '<div style="margin-bottom:22px;"><div style="font-size:20px;font-weight:600;">Bonjour ' + esc((state.me && state.me.username) || '') + ' 👋</div><div style="font-size:14px;color:var(--text-tertiary);margin-top:2px;">Voici l\'activité récente de classification des verbatims.</div></div>' +
      '<div style="display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;margin-bottom:22px;background:#fff;">' + kpis + '</div>' +
      '<div style="display:grid;grid-template-columns:1.5fr 1fr;gap:20px;">' +
        '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;background:#fff;"><div style="display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-bottom:1px solid var(--border-secondary);background:var(--gray-25);"><div style="font-size:13.5px;font-weight:600;">Derniers lots</div><div data-click="go" data-arg="lots" style="font-size:12.5px;font-weight:600;color:var(--brand-700);cursor:pointer;">Tout voir →</div></div>' + recent + '</div>' +
        '<div style="display:flex;flex-direction:column;gap:20px;"><div style="border:1px solid var(--border-primary);border-radius:8px;background:#fff;padding:16px;"><div style="font-size:13.5px;font-weight:600;margin-bottom:14px;">Moteur de classification</div><div style="display:flex;align-items:center;gap:11px;margin-bottom:14px;"><div style="width:40px;height:40px;border-radius:9px;background:var(--brand-50);display:grid;place-items:center;flex:none;box-shadow:inset 0 0 0 6px var(--brand-100);"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7f56d9" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h9l-1 8 10-12h-9z"/></svg></div><div><div style="font-size:14px;font-weight:600;">' + esc(mName) + '</div><div style="font-size:12px;color:var(--text-quaternary);">' + esc(mKind) + '</div></div><span style="margin-left:auto;">' + avail + '</span></div>' +
          f1row('F1 thème niv.1', m.f1_macro_niv1) + f1row('Précision sentiment', m.accuracy_sentiment) + f1row('Rappel rupture', m.recall_rupture, true) + '</div>' +
          '<div style="border:1px solid var(--border-primary);border-radius:8px;background:#fff;padding:16px;display:flex;flex-direction:column;gap:10px;"><div style="font-size:13.5px;font-weight:600;margin-bottom:2px;">Raccourcis</div>' +
          shortcut('new', 'M12 5v14M5 12h14', 'Lancer un nouveau lot') + shortcut('dashboards', 'M12 20V10M18 20V4M6 20v-6', 'Ouvrir les tableaux de bord') + shortcut('test', 'M9 3h6M10 3v6l-4 9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1l-4-9V3', 'Tester un verbatim à la volée') + '</div></div>' +
      '</div></div>';
  }
  function shortcut(route, path, label) {
    return '<button data-click="go" data-arg="' + route + '" class="h-soft" style="display:flex;align-items:center;gap:10px;width:100%;padding:11px 13px;border:1px solid var(--border-primary);background:#fff;border-radius:8px;font-size:13.5px;font-weight:600;color:var(--text-secondary);cursor:pointer;text-align:left;"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#7f56d9" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="' + path + '"/></svg>' + label + '</button>';
  }
  function wrap(inner, max) { return '<div style="max-width:' + (max || 1180) + 'px;">' + inner + '</div>'; }

  /* ================================================================ LOTS */
  function lots() {
    if (!state.batches) return wrap(loadingPanel('Chargement des lots…'), 1240);
    var rows = state.batches.map(mapBatch).map(function (b) {
      return '<div data-click="openBatch" data-arg="' + b.id + '" class="h-row" style="display:grid;grid-template-columns:60px 1fr 116px 156px 104px 90px 108px;align-items:center;padding:11px 16px;border-bottom:1px solid #f2f4f7;cursor:pointer;"><div style="font-family:' + MONO + ';font-size:12.5px;color:var(--text-quaternary);">' + b.id + '</div><div style="min-width:0;padding-right:14px;"><div style="font-size:13.5px;font-weight:500;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(b.label) + '</div><div style="font-size:11px;color:var(--text-quaternary);">' + esc(b.date) + '</div></div><div>' + batchStatusEl(b.status) + '</div><div style="padding-right:14px;">' + progEl(b.progress, b.status) + '</div><div style="font-family:' + MONO + ';font-size:12.5px;color:var(--text-secondary);">' + (b.count > 0 ? fmt(b.count) : '—') + '</div><div style="font-family:' + MONO + ';font-size:12.5px;color:var(--text-secondary);">' + (b.reviewPct > 0 ? pct1(b.reviewPct) : '—') + '</div><div style="font-size:12.5px;color:var(--text-tertiary);">' + esc(b.engine) + '</div></div>';
    }).join('');
    return wrap('<div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:18px;gap:16px;"><div><div style="font-size:19px;font-weight:600;">Lots de traitement</div><div style="font-size:13.5px;color:var(--text-tertiary);margin-top:2px;">' + state.batches.length + ' lots · classification automatique des verbatims par lots</div></div><button data-click="go" data-arg="new" class="h-brand" style="display:inline-flex;align-items:center;gap:7px;height:38px;padding:0 15px;background:var(--brand-600);color:#fff;border:none;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;box-shadow:var(--shadow-xs);"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>Nouveau lot</button></div>' +
      '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;background:#fff;"><div class="scrl" style="overflow-x:auto;"><div style="min-width:920px;"><div style="display:grid;grid-template-columns:60px 1fr 116px 156px 104px 90px 108px;background:var(--gray-50);border-bottom:1px solid var(--border-primary);padding:9px 16px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--text-quaternary);"><div>#</div><div>Libellé</div><div>Statut</div><div>Progression</div><div>Verbatims</div><div>% revue</div><div>Moteur</div></div>' + rows + '</div></div></div>', 1240);
  }

  /* ================================================================ NOUVEAU LOT */
  function dropZoneHTML(file, title, sub, act) {
    if (file) return '<div data-click="' + act + '" style="display:flex;align-items:center;gap:11px;padding:16px;border:1px solid #abefc6;border-radius:8px;background:#f6fef9;cursor:pointer;"><div style="width:34px;height:34px;border-radius:7px;background:#fff;border:1px solid #abefc6;display:grid;place-items:center;flex-shrink:0;">' + ic('doc', { size: 17, color: '#079455' }) + '</div><div style="min-width:0;flex:1;"><div style="font-size:13px;font-weight:600;color:#101828;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(file.name) + '</div><div style="font-size:11.5px;color:#667085;">' + esc(title) + (file.size ? ' · ' + esc(file.size) : '') + '</div></div><div style="flex-shrink:0;">' + ic('check', { size: 18, color: '#079455', stroke: 2.4 }) + '</div></div>';
    return '<div data-click="' + act + '" style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;padding:20px 16px;border:1.5px dashed #d0d5dd;border-radius:8px;background:#fcfcfd;cursor:pointer;text-align:center;"><div style="width:36px;height:36px;border-radius:8px;background:#f4ebff;display:grid;place-items:center;">' + ic('upload', { size: 18, color: '#7f56d9' }) + '</div><div style="font-size:13px;font-weight:600;color:#344054;">' + esc(title) + '</div><div style="font-size:11.5px;color:#667085;">' + esc(sub) + '</div><div style="font-size:11px;color:#98a2b3;margin-top:2px;">Cliquer pour déposer un .xlsx</div></div>';
  }
  function stepText() { var p = state.nbProgress; return p < 25 ? 'Anonymisation & nettoyage du texte' : (p < 55 ? 'Classification des thèmes (niv.1 → niv.2)' : (p < 82 ? 'Détection du sentiment & des signaux' : 'Calcul des scores de confiance')); }
  function newBatch() {
    var back = '<div data-click="go" data-arg="lots" class="h-back" style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-quaternary);cursor:pointer;margin-bottom:14px;"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>Retour aux lots</div>';
    var head = '<div style="font-size:19px;font-weight:600;margin-bottom:4px;">Nouveau lot de traitement</div><div style="font-size:13.5px;color:var(--text-tertiary);margin-bottom:22px;">Déposez les exports Excel des deux sources. Le traitement est asynchrone — vous pouvez quitter la page.</div>';
    var body;
    if (state.nbRunning) {
      body = '<div style="border:1px solid var(--border-primary);border-radius:8px;background:#fff;padding:26px;"><div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;"><span style="width:10px;height:10px;border-radius:50%;background:var(--brand-500);animation:pulse 1.2s infinite;"></span><div style="font-size:15px;font-weight:600;">Traitement en cours…</div><span style="margin-left:auto;font-family:' + MONO + ';font-size:11px;color:var(--text-quaternary);background:var(--gray-100);padding:2px 8px;border-radius:4px;">Lot #' + esc(state.nbBatchId || '—') + '</span></div><div style="height:12px;background:var(--gray-100);border-radius:9999px;overflow:hidden;margin-bottom:10px;"><div id="nbBar" style="width:' + state.nbProgress + '%;height:100%;background:linear-gradient(90deg,#9e77ed,#7f56d9);border-radius:9999px;transition:width .2s;"></div></div><div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:22px;"><span id="nbStep" style="color:var(--text-tertiary);">' + stepText() + '</span><span id="nbPct" style="font-family:' + MONO + ';font-weight:600;color:var(--text-secondary);">' + Math.round(state.nbProgress) + ' %</span></div><button data-click="cancel" class="h-danger" style="display:inline-flex;align-items:center;gap:7px;height:38px;padding:0 15px;background:#fff;color:var(--error-700);border:1px solid #fecdca;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>Annuler le traitement</button></div>';
    } else if (state.nbDone) {
      body = '<div style="border:1px solid #abefc6;border-radius:8px;background:var(--success-50);padding:26px;text-align:center;"><div style="width:48px;height:48px;border-radius:50%;background:#fff;border:1px solid #abefc6;display:grid;place-items:center;margin:0 auto 14px;"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#079455" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></div><div style="font-size:16px;font-weight:600;color:var(--success-700);margin-bottom:4px;">Traitement terminé</div><div style="font-size:13.5px;color:var(--text-tertiary);margin-bottom:18px;">Les verbatims ont été classés.</div><div style="display:flex;gap:10px;justify-content:center;"><button data-click="openBatch" data-arg="' + esc(state.nbBatchId || '') + '" class="h-brand" style="height:38px;padding:0 16px;background:var(--brand-600);color:#fff;border:none;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;">Voir le lot</button><button data-click="resetNb" class="h-soft" style="height:38px;padding:0 16px;background:#fff;color:var(--text-secondary);border:1px solid var(--border-primary);border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;">Lancer un autre lot</button></div></div>';
    } else {
      var hasFile = !!(state.nbMDTC || state.nbMopinion);
      var launchStyle = 'display:inline-flex;align-items:center;gap:8px;height:42px;padding:0 18px;border:none;border-radius:8px;font-size:14px;font-weight:600;box-shadow:var(--shadow-xs);' + (hasFile ? 'background:#7f56d9;color:#fff;cursor:pointer;' : 'background:#e4e7ec;color:#98a2b3;cursor:not-allowed;');
      var errBox = state.nbError ? errorPanel(state.nbError) + '<div style="height:14px;"></div>' : '';
      body = errBox + '<div style="border:1px solid var(--border-primary);border-radius:8px;background:#fff;padding:22px;"><input id="fileMDTC" type="file" accept=".xlsx" data-change="fileMDTC" style="display:none" /><input id="fileMopinion" type="file" accept=".xlsx" data-change="fileMopinion" style="display:none" /><div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:12px;">Fichiers source</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px;">' + dropZoneHTML(state.nbMDTC, 'MDTC', 'Export post-commande', 'pickMDTC') + dropZoneHTML(state.nbMopinion, 'Mopinion', 'Avis sur site', 'pickMopinion') + '</div><div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Libellé du lot <span style="color:var(--text-quaternary);font-weight:400;">(optionnel)</span></div><input data-f="nbLabel" data-input="nbLabel" value="' + esc(state.nbLabel) + '" placeholder="ex. Avis juin 2026" style="width:100%;height:40px;padding:0 12px;border:1px solid var(--border-primary);border-radius:8px;font-size:14px;box-shadow:var(--shadow-xs);margin-bottom:22px;" /><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;"><div style="font-size:13px;font-weight:600;color:var(--text-secondary);">Seuil de revue</div><div id="nbSeuilLabel" style="font-family:' + MONO + ';font-size:14px;font-weight:600;color:var(--brand-700);background:var(--brand-50);padding:2px 10px;border-radius:6px;">' + dec(state.nbSeuil) + '</div></div><input data-f="nbSeuil" data-input="nbSeuil" type="range" min="0" max="1" step="0.01" value="' + state.nbSeuil + '" style="width:100%;accent-color:#7f56d9;margin-bottom:4px;" /><div style="display:flex;justify-content:space-between;font-size:11.5px;color:var(--text-quaternary);margin-bottom:24px;"><span>0,00 — tout en auto</span><span>Sous ce score, le verbatim part en revue humaine</span><span>1,00</span></div><div style="display:flex;gap:10px;align-items:center;"><button data-click="launch" style="' + launchStyle + '"><svg width="16" height="16" viewBox="0 0 24 24" fill="#fff" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3v18l15-9L5 3z"/></svg>Lancer le traitement</button><span style="font-size:12.5px;color:var(--text-quaternary);">' + (hasFile ? '' : 'Déposez au moins un fichier pour lancer') + '</span></div></div>';
    }
    return '<div style="max-width:760px;">' + back + head + body + '</div>';
  }

  /* ================================================================ DÉTAIL */
  function detail() {
    if (state.detailLoading || !state.detailObj) return wrap(loadingPanel('Chargement du lot…'), 1240);
    if (state.error) return wrap(errorPanel(state.error), 1240);
    var b = mapBatch(state.detailObj);
    var revTotal = state.reviewQueue ? state.reviewQueue.total : 0;
    var dTab = state.detailTab;
    var tabs = '<div style="display:flex;gap:3px;border-bottom:1px solid var(--border-secondary);margin-bottom:22px;"><div data-click="detailTab" data-arg="dashboard" style="' + tabSt(dTab === 'dashboard') + '">Tableau de bord</div><div data-click="detailTab" data-arg="results" style="' + tabSt(dTab === 'results') + '">Résultats</div><div data-click="detailTab" data-arg="review" style="' + tabSt(dTab === 'review') + '">Revue <span style="font-size:11px;font-family:' + MONO + ';background:#fffaeb;color:#b54708;padding:1px 7px;border-radius:9999px;font-weight:600;">' + revTotal + '</span></div></div>';
    var tabBody = dTab === 'dashboard' ? detailDashboard() : (dTab === 'results' ? detailResults() : detailReview());
    return wrap('<div data-click="go" data-arg="lots" class="h-back" style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-quaternary);cursor:pointer;margin-bottom:12px;"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>Lots <span style="color:var(--gray-300);">/</span> <span style="font-family:' + MONO + ';">#' + esc(b.id) + '</span></div>' +
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px;"><div style="display:flex;align-items:center;gap:12px;min-width:0;"><h2 style="font-size:21px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(b.label) + '</h2><span style="flex:none;">' + batchStatusEl(b.status) + '</span><span style="flex:none;padding:2px 9px;border-radius:4px;background:var(--gray-100);color:var(--text-secondary);border:1px solid var(--border-secondary);font-size:11px;font-weight:600;font-family:' + MONO + ';">' + esc(b.engine) + '</span></div></div>' + tabs + tabBody, 1240);
  }
  function matrixTable(ts) {
    var entries = Object.keys(ts || {}).map(function (niv1) { var v = ts[niv1] || {}; var neg = v['Négatif'] || 0, neu = v['Neutre'] || 0, pos = v['Positif'] || 0; return { name: niv1, neg: neg, neu: neu, pos: pos, tot: neg + neu + pos }; }).sort(function (a, b) { return b.tot - a.tot; }).slice(0, 5);
    var rows = entries.map(function (m) { return '<div style="display:grid;grid-template-columns:1fr 90px 90px 90px 90px;align-items:center;padding:9px 16px;border-bottom:1px solid var(--border-tertiary);font-size:12.5px;"><span style="color:var(--text-secondary);font-weight:500;">' + esc(m.name) + '</span><span style="text-align:center;font-family:' + MONO + ';">' + fmt(m.neg) + '</span><span style="text-align:center;font-family:' + MONO + ';">' + fmt(m.neu) + '</span><span style="text-align:center;font-family:' + MONO + ';">' + fmt(m.pos) + '</span><span style="text-align:center;font-family:' + MONO + ';font-weight:600;">' + fmt(m.tot) + '</span></div>'; }).join('') || '<div style="padding:16px;color:var(--text-quaternary);font-size:12.5px;">Aucune donnée.</div>';
    return '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;"><div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-tertiary);padding:10px 16px;background:var(--gray-50);border-bottom:1px solid var(--border-secondary);">Thème × sentiment (top 5)</div><div class="scrl" style="overflow-x:auto;"><div style="min-width:560px;"><div style="display:grid;grid-template-columns:1fr 90px 90px 90px 90px;padding:8px 16px;border-bottom:1px solid var(--border-secondary);font-size:11px;font-weight:600;text-transform:uppercase;color:var(--text-quaternary);"><span></span><span style="text-align:center;">Négatif</span><span style="text-align:center;">Neutre</span><span style="text-align:center;">Positif</span><span style="text-align:center;">Total</span></div>' + rows + '</div></div></div>';
  }
  function kpiCell(label, value, color, border) { return '<div style="padding:14px 16px;' + (border ? 'border-right:1px solid var(--border-secondary);' : '') + '"><div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:7px;">' + label + '</div><div style="font-size:24px;font-weight:600;font-family:' + MONO + ';' + (color ? 'color:' + color + ';' : '') + '">' + value + '</div></div>'; }
  function sentRow(c, label, val, mt) { return '<div style="display:flex;justify-content:space-between;font-size:12.5px;' + (mt ? 'margin-top:7px;' : '') + '"><span style="display:flex;align-items:center;gap:6px;color:var(--text-tertiary);"><span style="width:8px;height:8px;border-radius:2px;background:' + c + ';"></span>' + label + '</span><span style="font-family:' + MONO + ';font-weight:600;">' + val + '</span></div>'; }
  function sigRow(c, label, val, border) { return '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;' + (border ? 'border-bottom:1px solid var(--border-tertiary);' : '') + 'font-size:12.5px;"><span style="display:flex;align-items:center;gap:8px;"><span style="width:8px;height:8px;border-radius:50%;background:' + c + ';"></span>' + label + '</span><span style="font-family:' + MONO + ';font-weight:600;">' + val + '</span></div>'; }
  function detailDashboard() {
    var k = state.detailKpi;
    if (!k) return loadingPanel('Chargement des indicateurs…');
    var THEME_COLORS = ['#7f56d9', '#8a63dd', '#9e77ed', '#b692f6', '#d6bbfb', '#e9d7fe'];
    var themeEntries = Object.keys(k.themes || {}).map(function (n) { return [n, k.themes[n]]; }).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 6);
    var maxT = themeEntries.reduce(function (a, e) { return Math.max(a, e[1]); }, 1);
    var themeBars = themeEntries.map(function (e, i) { var pctw = Math.round(e[1] / maxT * 100); return '<div style="display:flex;align-items:center;gap:12px;font-size:12.5px;"><div style="width:118px;color:var(--text-tertiary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(e[0]) + '</div><div style="flex:1;height:14px;background:var(--gray-100);border-radius:3px;overflow:hidden;"><div style="width:' + pctw + '%;height:100%;background:' + THEME_COLORS[i % THEME_COLORS.length] + ';border-radius:3px;"></div></div><div style="width:46px;text-align:right;font-family:' + MONO + ';color:var(--text-secondary);">' + fmt(e[1]) + '</div></div>'; }).join('') || '<div style="color:var(--text-quaternary);font-size:12.5px;">Aucune donnée.</div>';
    var s = k.sentiments || {}; var sNeg = s['Négatif'] || 0, sNeu = s['Neutre'] || 0, sPos = s['Positif'] || 0, sTot = sNeg + sNeu + sPos || 1;
    var pN = Math.round(sNeg / sTot * 100), pU = Math.round(sNeu / sTot * 100), pP = 100 - pN - pU;
    var sig = k.signals || {};
    return '<div style="display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;margin-bottom:20px;background:#fff;">' +
      kpiCell('Volume', fmt(k.n_total), '', true) + kpiCell('En revue', pct1((k.review_rate || 0) * 100), 'var(--warning-700)', true) + kpiCell('Erreurs', fmt(k.n_errors), k.n_errors ? 'var(--error-700)' : '', true) + kpiCell('Durée', fmtDuration(k.duration_s), '', false) + '</div>' +
      '<div style="display:grid;grid-template-columns:1.4fr 1fr;gap:18px;margin-bottom:18px;"><div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;"><div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-tertiary);padding:10px 16px;background:var(--gray-50);border-bottom:1px solid var(--border-secondary);">Distribution des thèmes (niv.1)</div><div style="padding:14px 16px;display:flex;flex-direction:column;gap:10px;">' + themeBars + '</div></div>' +
      '<div style="display:flex;flex-direction:column;gap:18px;"><div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;"><div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-tertiary);padding:10px 16px;background:var(--gray-50);border-bottom:1px solid var(--border-secondary);">Sentiments</div><div style="padding:14px 16px;"><div style="display:flex;height:13px;border-radius:9999px;overflow:hidden;margin-bottom:14px;"><div style="width:' + pN + '%;background:var(--error-500);"></div><div style="width:' + pU + '%;background:var(--gray-300);"></div><div style="width:' + pP + '%;background:var(--success-500);"></div></div>' + sentRow('var(--error-500)', 'Négatif', pN + ' %') + sentRow('var(--gray-300)', 'Neutre', pU + ' %', true) + sentRow('var(--success-500)', 'Positif', pP + ' %', true) + '</div></div>' +
      '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;"><div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-tertiary);padding:10px 16px;background:var(--gray-50);border-bottom:1px solid var(--border-secondary);">Signaux d\'alerte</div><div style="padding:6px 16px;">' + sigRow('#b42318', 'Rupture client', fmt(sig.rupture || 0), true) + sigRow('#b54708', 'Churn', fmt(sig.churn || 0), true) + sigRow('#c01573', 'Insatisfaction forte', fmt(sig.insatisfaction || 0), false) + '</div></div></div></div>' + matrixTable(k.theme_sentiment);
  }
  function exportBtn(act, label) { return '<button data-click="' + act + '" class="h-soft" style="display:inline-flex;align-items:center;gap:6px;height:38px;padding:0 12px;background:#fff;border:1px solid var(--border-primary);border-radius:8px;font-size:13px;font-weight:600;color:var(--text-secondary);cursor:pointer;"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>' + label + '</button>'; }
  function detailResults() {
    var selStyle = 'height:38px;padding:0 10px;border:1px solid var(--border-primary);border-radius:8px;font-size:13.5px;background:#fff;color:var(--text-secondary);box-shadow:var(--shadow-xs);';
    var filters = '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;"><div style="position:relative;flex:1;min-width:220px;"><span style="position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--text-quaternary);"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg></span><input data-f="fText" data-input="fText" value="' + esc(state.fText) + '" placeholder="Rechercher dans les verbatims…" style="width:100%;height:38px;padding:0 12px 0 34px;border:1px solid var(--border-primary);border-radius:8px;font-size:13.5px;box-shadow:var(--shadow-xs);" /></div>' +
      '<input data-f="fTheme" data-input="fTheme" value="' + esc(state.fTheme) + '" placeholder="Thème…" style="width:140px;height:38px;padding:0 12px;border:1px solid var(--border-primary);border-radius:8px;font-size:13.5px;box-shadow:var(--shadow-xs);" />' +
      '<select data-f="fSent" data-change="fSent" style="' + selStyle + '">' + options([['', 'Sentiment'], ['neg', 'Négatif'], ['neu', 'Neutre'], ['pos', 'Positif']], state.fSent) + '</select>' +
      '<select data-f="fSignal" data-change="fSignal" style="' + selStyle + '">' + options([['', 'Signaux'], ['RUP', 'Rupture client'], ['CHU', 'Churn'], ['INS', 'Insatisfaction forte']], state.fSignal) + '</select>' +
      '<select data-f="fStatus" data-change="fStatus" style="' + selStyle + '">' + options([['', 'Statut'], ['auto', 'Auto'], ['revue', 'À revoir'], ['corrige', 'Corrigé']], state.fStatus) + '</select>' +
      '<div style="display:flex;gap:8px;">' + exportBtn('exportCSV', 'CSV') + exportBtn('exportXLSX', 'XLSX') + '</div></div>';
    var inner;
    if (state.resultsLoading || !state.results) inner = loadingPanel('Chargement des résultats…');
    else {
      var items = (state.results.items || []).map(mapResult);
      if (state.fStatus === 'corrige') items = items.filter(function (v) { return v.status === 'corrige'; });
      var rows = items.map(function (v) {
        return '<div style="display:grid;grid-template-columns:1fr 184px 96px 96px 122px 92px;align-items:center;padding:11px 16px;border-bottom:1px solid var(--border-tertiary);font-size:13px;"><div style="padding-right:16px;color:var(--text-secondary);">' + anonText(v.text) + '<span style="font-size:10.5px;color:var(--text-quaternary);font-family:' + MONO + ';margin-left:6px;">' + esc(v.src) + '</span></div><div style="font-size:12px;"><div style="color:var(--text-secondary);font-weight:500;">' + esc(v.t1) + ' <span style="font-family:' + MONO + ';color:var(--text-quaternary);font-weight:400;">' + dec(v.tc1) + '</span></div><div style="color:var(--text-quaternary);">' + esc(v.t2) + '</div></div><div>' + sentEl(v.sent) + '</div><div>' + sigEls(v.sig) + '</div><div style="padding-right:10px;">' + confEl(v.conf) + '</div><div>' + statusVerb(v.status) + '</div></div>';
      }).join('');
      var noRes = items.length === 0 ? '<div style="padding:48px 16px;text-align:center;color:var(--text-quaternary);"><div style="width:42px;height:42px;border-radius:9px;background:var(--gray-50);border:1px solid var(--border-secondary);display:grid;place-items:center;margin:0 auto 12px;"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#98a2b3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg></div><div style="font-size:14px;font-weight:600;color:var(--text-secondary);">Aucun verbatim ne correspond</div><div style="font-size:13px;margin-top:3px;">Ajustez ou réinitialisez les filtres.</div></div>' : '';
      var total = state.results.total, off = state.results.offset || 0, lim = state.results.limit || 50;
      var from = total ? off + 1 : 0, to = Math.min(off + lim, total);
      var prevDis = off <= 0, nextDis = off + lim >= total;
      inner = '<div class="scrl" style="overflow-x:auto;"><div style="min-width:1000px;"><div style="display:grid;grid-template-columns:1fr 184px 96px 96px 122px 92px;background:var(--gray-50);border-bottom:1px solid var(--border-primary);padding:9px 16px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--text-quaternary);"><div>Verbatim (anonymisé)</div><div>Thème</div><div>Sentiment</div><div>Signaux</div><div>Confiance</div><div>Statut</div></div>' + rows + noRes + '</div></div>' +
        '<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-top:1px solid var(--border-secondary);background:var(--gray-25);font-size:12.5px;color:var(--text-quaternary);"><span><span style="font-family:' + MONO + ';font-weight:600;color:var(--text-secondary);">' + from + '–' + to + '</span> sur ' + fmt(total) + ' verbatims</span><div style="display:flex;align-items:center;gap:6px;"><span data-click="resPrev" style="padding:3px 9px;border:1px solid var(--border-primary);border-radius:6px;background:#fff;cursor:' + (prevDis ? 'default' : 'pointer') + ';opacity:' + (prevDis ? '.5' : '1') + ';">‹ Préc.</span><span data-click="resNext" style="padding:3px 9px;border:1px solid var(--border-primary);border-radius:6px;background:#fff;cursor:' + (nextDis ? 'default' : 'pointer') + ';opacity:' + (nextDis ? '.5' : '1') + ';">Suivant ›</span></div></div>';
    }
    return filters + '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;background:#fff;">' + inner + '</div>';
  }
  function detailReview() {
    var rq = state.reviewQueue;
    if (!rq) return loadingPanel('Chargement de la file de revue…');
    var items = (rq.items || []).map(mapResult);
    var revIdx = Math.min(state.revIdx, Math.max(0, items.length - 1));
    var cur = items[revIdx];
    var queue = items.map(function (v, i) {
      var bg = i === revIdx ? '#f9f5ff' : 'transparent', sh = i === revIdx ? 'inset 2px 0 0 #7f56d9' : 'none';
      return '<div data-click="revGo" data-arg="' + i + '" class="h-row" style="display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #f2f4f7;cursor:pointer;background:' + bg + ';box-shadow:' + sh + ';"><div style="min-width:0;flex:1;"><div style="font-size:12.5px;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(v.text) + '</div><div style="font-size:10.5px;color:var(--text-quaternary);font-family:' + MONO + ';">#' + v.id + ' · ' + esc(v.src) + '</div></div><span style="flex:none;">' + confEl(v.conf) + '</span></div>';
    }).join('') || '<div style="padding:16px;color:var(--text-quaternary);font-size:12.5px;">File vide.</div>';
    var queueBox = '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;background:#fff;"><div style="display:flex;align-items:center;justify-content:space-between;padding:11px 14px;background:var(--gray-50);border-bottom:1px solid var(--border-secondary);"><span style="font-size:12.5px;font-weight:600;color:var(--text-secondary);">File de revue</span><span style="font-size:11px;font-family:' + MONO + ';color:var(--text-quaternary);">tri : moins confiant</span></div>' + queue + '</div>';
    var right;
    if (cur) {
      if (!state.revForm || state.revForm.id !== cur.id) state.revForm = { id: cur.id, t1: cur.t1, t2: cur.t2, sent: cur.sent, sig: cur.sig.slice() };
      var rf = state.revForm, TH = themesMap();
      var t1opts = options(Object.keys(TH).map(function (k) { return [k, k]; }), rf.t1);
      var t2opts = options((TH[rf.t1] || []).map(function (k) { return [k, k]; }), rf.t2);
      right = '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;background:#fff;"><div style="display:flex;align-items:center;justify-content:space-between;padding:12px 18px;border-bottom:1px solid var(--border-secondary);background:var(--gray-25);"><span style="font-size:12.5px;font-weight:600;color:var(--text-secondary);">Verbatim <span style="font-family:' + MONO + ';color:var(--text-quaternary);">#' + cur.id + '</span> · ' + esc(cur.src) + '</span><span style="font-size:12px;color:var(--text-quaternary);">' + (revIdx + 1) + ' / ' + items.length + ' · confiance <span style="font-family:' + MONO + ';font-weight:600;color:var(--warning-700);">' + dec(cur.conf) + '</span></span></div><div style="padding:18px;"><div style="background:var(--gray-50);border:1px solid var(--border-secondary);border-radius:8px;padding:14px 16px;font-size:14px;line-height:1.5;color:var(--text-primary);margin-bottom:20px;">' + anonText(cur.text) + '</div>' +
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px;"><div><div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Thème niv.1</div><select data-change="revT1" style="width:100%;height:40px;padding:0 10px;border:1px solid var(--border-primary);border-radius:8px;font-size:13.5px;background:#fff;box-shadow:var(--shadow-xs);">' + t1opts + '</select></div><div><div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Thème niv.2 <span style="color:var(--text-quaternary);font-weight:400;">(selon niv.1)</span></div><select data-change="revT2" style="width:100%;height:40px;padding:0 10px;border:1px solid var(--border-primary);border-radius:8px;font-size:13.5px;background:#fff;box-shadow:var(--shadow-xs);">' + t2opts + '</select></div></div>' +
        '<div style="margin-bottom:18px;"><div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Sentiment</div><div style="display:flex;gap:8px;"><div data-click="revSent" data-arg="neg" style="' + seg(rf.sent === 'neg', '#b42318', '#fef3f2') + '">Négatif</div><div data-click="revSent" data-arg="neu" style="' + seg(rf.sent === 'neu', '#344054', '#f2f4f7') + '">Neutre</div><div data-click="revSent" data-arg="pos" style="' + seg(rf.sent === 'pos', '#067647', '#ecfdf3') + '">Positif</div></div></div>' +
        '<div style="margin-bottom:22px;"><div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Signaux d\'alerte</div><div style="display:flex;gap:8px;flex-wrap:wrap;"><div data-click="revSig" data-arg="RUP" style="' + seg(rf.sig.indexOf('RUP') >= 0, '#b42318', '#fef3f2') + '">Rupture client</div><div data-click="revSig" data-arg="CHU" style="' + seg(rf.sig.indexOf('CHU') >= 0, '#b54708', '#fffaeb') + '">Churn</div><div data-click="revSig" data-arg="INS" style="' + seg(rf.sig.indexOf('INS') >= 0, '#c01573', '#fce7f0') + '">Insatisfaction forte</div></div></div>' +
        '<div style="display:flex;align-items:center;gap:12px;padding-top:16px;border-top:1px solid var(--border-secondary);"><button data-click="revValidate" class="h-brand" style="display:inline-flex;align-items:center;gap:7px;height:40px;padding:0 18px;background:var(--brand-600);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;box-shadow:var(--shadow-xs);"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>Valider la correction</button><button data-click="exportCorr" class="h-soft" style="display:inline-flex;align-items:center;gap:7px;height:40px;padding:0 14px;background:#fff;color:var(--text-secondary);border:1px solid var(--border-primary);border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>Exporter les corrections</button></div></div></div>';
    } else {
      right = '<div style="border:1px solid #abefc6;border-radius:8px;background:var(--success-50);padding:40px;text-align:center;"><div style="width:46px;height:46px;border-radius:50%;background:#fff;border:1px solid #abefc6;display:grid;place-items:center;margin:0 auto 12px;"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#079455" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></div><div style="font-size:15px;font-weight:600;color:var(--success-700);">File de revue vide</div><div style="font-size:13px;color:var(--text-tertiary);margin-top:3px;">Tous les verbatims sous le seuil ont été corrigés et validés.</div></div>';
    }
    return '<div style="display:grid;grid-template-columns:300px 1fr;gap:18px;align-items:start;">' + queueBox + right + '</div>';
  }

  /* ================================================================ DASHBOARDS */
  function dashboards() {
    if (!state.modelKpi || !state.volumetry) return wrap(loadingPanel('Chargement des tableaux de bord…'), 1200);
    var mk = state.modelKpi.active, m = (mk && mk.metrics) || {};
    var cards = [['F1 thème niv.1', m.f1_macro_niv1, 0.80], ['F1 thème niv.2', m.f1_macro_niv2, 0.70], ['Précision sentiment', m.accuracy_sentiment, 0.85], ['Rappel rupture', m.recall_rupture, 0.75]].map(function (k) {
      var v = k[1], below = v != null && v < k[2];
      var flag = v == null ? tag('n/d', '#f2f4f7', '#475467', { fs: 10, fw: 600 }) : (below ? tag('⚠ sous cible', '#fef3f2', '#b42318', { fs: 10, fw: 600 }) : tag('OK', '#ecfdf3', '#067647', { fs: 10, fw: 600 }));
      return '<div style="border:1px solid ' + (below ? '#fecdca' : '#e4e7ec') + ';border-radius:8px;padding:16px;background:' + (below ? '#fffbfa' : '#fff') + ';"><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;"><span style="font-size:12.5px;color:var(--text-tertiary);">' + k[0] + '</span><span>' + flag + '</span></div><div style="font-size:28px;font-weight:600;font-family:' + MONO + ';color:' + (below ? '#b42318' : '#101828') + ';line-height:1;">' + (v == null ? '—' : dec(v)) + '</div><div style="font-size:11.5px;color:var(--text-quaternary);margin-top:7px;">cible ' + dec(k[2]) + '</div></div>';
    }).join('');
    var series = state.volumetry.series || [];
    var maxV = series.reduce(function (a, s) { return Math.max(a, s.n_total); }, 1);
    var monthly = series.map(function (s) {
      var label = s.label || fmtDate(s.created_at); var h = Math.round(s.n_total / maxV * 128);
      return '<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:8px;height:100%;justify-content:flex-end;"><div style="font-size:11px;font-family:' + MONO + ';color:var(--text-quaternary);">' + (s.n_total / 1000).toFixed(1).replace('.', ',') + 'k</div><div style="width:64%;height:' + h + 'px;background:#7f56d9;border-radius:4px 4px 0 0;"></div><div style="font-size:11.5px;color:var(--text-tertiary);">' + esc(label) + '</div></div>';
    }).join('') || '<div style="color:var(--text-quaternary);font-size:12.5px;">Aucun lot terminé.</div>';
    var gt = state.volumetry.global_themes || {};
    var topThemes = Object.keys(gt).map(function (n) { return [n, gt[n]]; }).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 5);
    var topDelta = topThemes.map(function (t) { return '<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border-tertiary);font-size:13px;"><span style="color:var(--text-secondary);font-weight:500;">' + esc(t[0]) + '</span><span style="font-family:' + MONO + ';color:var(--text-quaternary);">' + fmt(t[1]) + '</span></div>'; }).join('') || '<div style="padding:10px 0;color:var(--text-quaternary);font-size:12.5px;">Aucune donnée.</div>';
    return wrap('<div style="margin-bottom:18px;"><div style="font-size:19px;font-weight:600;">Tableaux de bord</div><div style="font-size:13.5px;color:var(--text-tertiary);margin-top:2px;">Performance du modèle actif et tendances · agrégé sur les lots terminés</div></div>' +
      '<div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:10px;">Qualité du modèle · ' + esc(mk ? mk.label : '—') + '</div><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px;">' + cards + '</div>' +
      '<div style="display:grid;grid-template-columns:1.4fr 1fr;gap:18px;margin-bottom:18px;"><div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;"><div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-tertiary);padding:10px 16px;background:var(--gray-50);border-bottom:1px solid var(--border-secondary);">Volumétrie par lot</div><div style="padding:20px 16px 12px;display:flex;align-items:flex-end;gap:14px;height:200px;">' + monthly + '</div></div>' +
      '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;"><div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-tertiary);padding:10px 16px;background:var(--gray-50);border-bottom:1px solid var(--border-secondary);">Top thèmes (global)</div><div style="padding:6px 16px;">' + topDelta + '</div></div></div>' + matrixTable(state.volumetry.theme_sentiment), 1200);
  }

  /* ================================================================ TEST */
  function testScreen() {
    var tr = state.testRes, resPanel;
    if (state.testLoading) resPanel = '<div style="padding:18px;"><div style="height:14px;width:60%;background:var(--gray-100);border-radius:6px;margin-bottom:14px;animation:pulse 1.1s infinite;"></div><div style="height:34px;background:var(--gray-100);border-radius:6px;margin-bottom:12px;animation:pulse 1.1s infinite;"></div><div style="height:34px;background:var(--gray-100);border-radius:6px;margin-bottom:12px;animation:pulse 1.1s infinite;"></div><div style="height:14px;width:40%;background:var(--gray-100);border-radius:6px;animation:pulse 1.1s infinite;"></div></div>';
    else if (tr) {
      var conf = typeof tr.confidence_globale === 'number' ? tr.confidence_globale : parseFloat(tr.confidence_globale) || 0;
      var sg = []; if (tr.signal_rupture_client) sg.push('RUP'); if (tr.signal_churn) sg.push('CHU'); if (tr.signal_insatisfaction_forte) sg.push('INS');
      resPanel = '<div style="padding:18px;"><div style="font-size:11.5px;color:var(--text-quaternary);margin-bottom:4px;">Thème</div><div style="font-size:15px;font-weight:600;margin-bottom:14px;">' + esc(tr.theme1_niv1) + ' <span style="color:var(--text-quaternary);font-weight:400;">›</span> ' + esc(tr.theme1_niv2) + '</div><div style="display:flex;gap:24px;margin-bottom:16px;"><div><div style="font-size:11.5px;color:var(--text-quaternary);margin-bottom:5px;">Sentiment</div>' + sentFull(sentKey(tr.theme1_sentiment)) + '</div><div><div style="font-size:11.5px;color:var(--text-quaternary);margin-bottom:5px;">Signaux</div>' + sigEls(sg) + '</div></div><div style="font-size:11.5px;color:var(--text-quaternary);margin-bottom:5px;">Confiance</div><div style="display:flex;align-items:center;gap:10px;"><div style="flex:1;">' + confEl(conf) + '</div></div><div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--border-tertiary);font-size:11.5px;color:var(--text-quaternary);display:flex;align-items:center;gap:6px;"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/></svg>Diagnostic — aucun enregistrement' + (tr.model_label ? ' · ' + esc(tr.model_label) : '') + '</div></div>';
    } else resPanel = '<div style="padding:40px 16px;text-align:center;color:var(--text-quaternary);font-size:13px;"><div style="width:40px;height:40px;border-radius:9px;background:var(--gray-50);border:1px solid var(--border-secondary);display:grid;place-items:center;margin:0 auto 12px;"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="#98a2b3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6l-4 9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1l-4-9V3"/></svg></div>Saisissez un verbatim puis lancez l\'analyse.</div>';
    return wrap('<div style="margin-bottom:18px;"><div style="font-size:19px;font-weight:600;">Test à la volée</div><div style="font-size:13.5px;color:var(--text-tertiary);margin-top:2px;">Analysez un verbatim isolé pour diagnostic. <strong style="color:var(--text-secondary);">Rien n\'est enregistré.</strong></div></div>' +
      '<div style="display:grid;grid-template-columns:1fr 380px;gap:18px;align-items:start;"><div style="border:1px solid var(--border-primary);border-radius:8px;background:#fff;padding:18px;"><div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Verbatim</div><textarea data-f="testText" data-input="testText" placeholder="Collez ou saisissez un avis client…" style="width:100%;height:140px;padding:12px;border:1px solid var(--border-primary);border-radius:8px;font-size:14px;line-height:1.5;resize:vertical;box-shadow:var(--shadow-xs);font-family:var(--font-body);">' + esc(state.testText) + '</textarea><div style="display:flex;align-items:center;gap:14px;margin-top:14px;"><div style="font-size:12px;font-weight:600;color:var(--text-secondary);">Note de satisfaction <span style="color:var(--text-quaternary);font-weight:400;">(optionnel)</span></div><select data-change="testNote" style="height:36px;padding:0 10px;border:1px solid var(--border-primary);border-radius:8px;font-size:13.5px;background:#fff;">' + options([['', '—'], ['1', '1 / 5'], ['2', '2 / 5'], ['3', '3 / 5'], ['4', '4 / 5'], ['5', '5 / 5']], state.testNote) + '</select></div><button data-click="runTest" class="h-brand" style="margin-top:18px;display:inline-flex;align-items:center;gap:8px;height:42px;padding:0 18px;background:var(--brand-600);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;box-shadow:var(--shadow-xs);"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6l-4 9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1l-4-9V3"/></svg>Analyser</button></div>' +
      '<div style="border:1px solid var(--border-primary);border-radius:8px;background:#fff;min-height:200px;"><div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-tertiary);padding:12px 16px;border-bottom:1px solid var(--border-secondary);">Résultat</div>' + resPanel + '</div></div>', 900);
  }

  /* ================================================================ AIDE */
  function help() {
    var steps = [
      ['1', 'Anonymisation', 'Noms, e-mails, téléphones et n° de commande sont remplacés par des marqueurs <span style="font-family:' + MONO + ';color:var(--brand-700);background:var(--brand-50);padding:0 3px;border-radius:3px;font-size:11px;">[NOM]</span>. Aucune donnée personnelle n\'est conservée.'],
      ['2', 'Nettoyage', 'Le texte est normalisé : ponctuation, casse, doublons et caractères parasites sont harmonisés pour le modèle.'],
      ['3', 'Classification', 'Le moteur attribue un thème niv.1 → niv.2, un sentiment et trois signaux d\'alerte.'],
      ['4', 'Score de confiance', 'Chaque prédiction reçoit un score 0–1. Sous le seuil, le verbatim est routé en revue.'],
      ['5', 'Revue humaine', 'Un analyste corrige les cas incertains : thème, sentiment, signaux. Le verbatim passe « corrigé ».'],
      ['6', 'Export', 'Les résultats (auto + corrigés) sont exportables en CSV / XLSX pour analyse aval.']
    ];
    var cards = steps.map(function (s) { return '<div style="border:1px solid var(--border-secondary);border-radius:8px;padding:16px;background:#fff;"><div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;"><span style="width:24px;height:24px;border-radius:6px;background:var(--brand-600);color:#fff;display:grid;place-items:center;font-size:12px;font-weight:700;font-family:' + MONO + ';">' + s[0] + '</span><span style="font-size:14px;font-weight:600;">' + s[1] + '</span></div><div style="font-size:12.5px;color:var(--text-tertiary);line-height:1.5;">' + s[2] + '</div></div>'; }).join('');
    return wrap('<div style="margin-bottom:22px;"><div style="font-size:19px;font-weight:600;">Comment ça marche</div><div style="font-size:13.5px;color:var(--text-tertiary);margin-top:2px;">Le parcours d\'un verbatim, de sa réception à l\'export, et les notions clés.</div></div><div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:14px;">Le pipeline de traitement</div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:28px;">' + cards + '</div>' +
      '<div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:14px;">Exemple concret</div><div style="border:1px solid var(--border-primary);border-radius:8px;background:#fff;padding:18px;display:grid;grid-template-columns:1fr 28px 1fr;align-items:center;gap:14px;"><div><div style="font-size:11.5px;color:var(--text-quaternary);margin-bottom:6px;">Verbatim brut</div><div style="background:var(--gray-50);border:1px solid var(--border-secondary);border-radius:8px;padding:12px 14px;font-size:13.5px;line-height:1.5;color:var(--text-secondary);">« Bonjour Marc Dupont, ma commande CMD-48213 n\'est jamais arrivée et personne ne répond au 06 12 34 56 78 ! »</div></div><div style="display:grid;place-items:center;color:var(--brand-500);"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg></div><div><div style="font-size:11.5px;color:var(--text-quaternary);margin-bottom:6px;">Après traitement</div><div style="background:#fff;border:1px solid var(--border-primary);border-radius:8px;padding:12px 14px;"><div style="font-size:13px;line-height:1.5;color:var(--text-secondary);margin-bottom:10px;">« Bonjour <span style="font-family:' + MONO + ';color:var(--brand-700);background:var(--brand-50);padding:0 3px;border-radius:3px;font-size:11px;">[NOM]</span>, ma commande <span style="font-family:' + MONO + ';color:var(--brand-700);background:var(--brand-50);padding:0 3px;border-radius:3px;font-size:11px;">[COMMANDE]</span> n\'est jamais arrivée… »</div><div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;"><span style="padding:1px 7px;border-radius:4px;background:var(--gray-100);color:var(--text-secondary);font-size:11px;font-weight:600;">Livraison › Retard</span><span style="padding:1px 7px;border-radius:4px;background:#fef3f2;color:#b42318;font-size:11px;font-weight:600;">NÉG</span><span style="padding:1px 7px;border-radius:4px;background:#fef3f2;color:#b42318;font-size:10px;font-weight:700;font-family:' + MONO + ';">RUP</span><span style="font-family:' + MONO + ';font-size:11px;color:var(--success-700);font-weight:600;">conf 0,93</span></div></div></div></div>', 980);
  }

  /* ================================================================ UTILISATEURS */
  function users() {
    if (!state.users) return wrap(loadingPanel('Chargement des comptes…'), 1000);
    var rows = state.users.map(function (u) {
      var roleEl = u.role === 'admin' ? tag('Admin', '#f9f5ff', '#6941c6', { pill: true, fs: 12, fw: 500 }) : tag('Analyste', '#f9fafb', '#344054', { pill: true, fs: 12, fw: 500, bd: '#eaecf0' });
      var statusEl = u.is_active ? tag('Actif', '#ecfdf3', '#067647', { pill: true, dot: true, fs: 12, fw: 500 }) : tag('Inactif', '#f9fafb', '#667085', { pill: true, dot: true, fs: 12, fw: 500, bd: '#eaecf0' });
      var aStyle = 'padding:5px 12px;border:1px solid ' + (u.is_active ? '#fecdca' : '#d0d5dd') + ';border-radius:7px;font-size:12px;font-weight:600;color:' + (u.is_active ? '#b42318' : '#475467') + ';cursor:pointer;display:inline-block;';
      return '<div style="display:grid;grid-template-columns:1fr 180px 120px 120px 150px;align-items:center;padding:11px 16px;border-bottom:1px solid var(--border-tertiary);"><div style="display:flex;align-items:center;gap:10px;"><div style="width:30px;height:30px;border-radius:50%;background:var(--brand-100);color:var(--brand-700);display:grid;place-items:center;font-size:11px;font-weight:600;">' + inits(u.username) + '</div><span style="font-size:13.5px;font-weight:500;color:var(--text-secondary);">' + esc(u.username) + '</span></div><div style="font-family:' + MONO + ';font-size:12.5px;color:var(--text-tertiary);">#' + u.id + '</div><div>' + roleEl + '</div><div>' + statusEl + '</div><div style="text-align:right;"><span data-click="userToggle" data-arg="' + u.id + '" style="' + aStyle + '">' + (u.is_active ? 'Désactiver' : 'Activer') + '</span></div></div>';
    }).join('');
    return wrap('<div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:18px;"><div><div style="font-size:19px;font-weight:600;">Utilisateurs</div><div style="font-size:13.5px;color:var(--text-tertiary);margin-top:2px;">' + state.users.length + ' comptes · gestion des accès et des rôles</div></div><button data-click="createUser" class="h-brand" style="display:inline-flex;align-items:center;gap:7px;height:38px;padding:0 15px;background:var(--brand-600);color:#fff;border:none;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;box-shadow:var(--shadow-xs);"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>Créer un compte</button></div>' +
      '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;background:#fff;"><div style="display:grid;grid-template-columns:1fr 180px 120px 120px 150px;background:var(--gray-50);border-bottom:1px solid var(--border-primary);padding:9px 16px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--text-quaternary);"><div>Utilisateur</div><div>Identifiant</div><div>Rôle</div><div>Statut</div><div style="text-align:right;">Actions</div></div>' + rows + '</div>', 1000);
  }

  /* ================================================================ ADMINISTRATION */
  function admin() {
    var at = state.adminTab;
    var tabs = '<div style="display:flex;gap:3px;border-bottom:1px solid var(--border-secondary);margin-bottom:22px;flex-wrap:wrap;"><div data-click="adminTab" data-arg="config" style="' + tabSt(at === 'config') + '">Configuration</div><div data-click="adminTab" data-arg="models" style="' + tabSt(at === 'models') + '">Modèles</div><div data-click="adminTab" data-arg="ops" style="' + tabSt(at === 'ops') + '">Exploitation</div><div data-click="adminTab" data-arg="retention" style="' + tabSt(at === 'retention') + '">Rétention</div><div data-click="adminTab" data-arg="audit" style="' + tabSt(at === 'audit') + '">Journal d\'audit</div></div>';
    var body;
    if (at === 'config') {
      body = '<div style="border:1px solid var(--border-primary);border-radius:8px;background:#fff;padding:22px;max-width:620px;"><div style="display:flex;align-items:center;justify-content:space-between;padding-bottom:16px;border-bottom:1px solid var(--border-tertiary);margin-bottom:16px;"><div><div style="font-size:14px;font-weight:600;">Durée de rétention</div><div style="font-size:12.5px;color:var(--text-tertiary);margin-top:2px;">Au-delà, les lots sont purgés automatiquement.</div></div><div style="display:flex;align-items:center;gap:8px;"><input data-f="cfgRetention" data-input="cfgRetention" type="number" value="' + esc(String(state.cfgRetention)) + '" style="width:72px;height:38px;padding:0 10px;border:1px solid var(--border-primary);border-radius:8px;font-size:14px;font-family:' + MONO + ';text-align:center;" /><span style="font-size:13px;color:var(--text-tertiary);">mois</span></div></div><div style="padding-bottom:8px;"><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;"><div><div style="font-size:14px;font-weight:600;">Seuil de revue par défaut</div><div style="font-size:12.5px;color:var(--text-tertiary);margin-top:2px;">Score sous lequel un verbatim part en revue humaine.</div></div><div id="cfgSeuilLabel" style="font-family:' + MONO + ';font-size:15px;font-weight:600;color:var(--brand-700);background:var(--brand-50);padding:2px 10px;border-radius:6px;">' + dec(state.cfgSeuil) + '</div></div><input data-f="cfgSeuil" data-input="cfgSeuil" type="range" min="0" max="1" step="0.01" value="' + state.cfgSeuil + '" style="width:100%;accent-color:#7f56d9;" /></div><button data-click="saveCfg" class="h-brand" style="margin-top:18px;height:38px;padding:0 16px;background:var(--brand-600);color:#fff;border:none;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;">Enregistrer</button></div>';
    } else if (at === 'models') {
      if (!state.models) body = loadingPanel('Chargement des moteurs…');
      else {
        var mrows = state.models.map(function (m) {
          var f1 = m.metrics && m.metrics.f1_macro_niv1 != null ? dec(m.metrics.f1_macro_niv1) : '—';
          var activeEl = m.is_active ? tag('Actif', '#f9f5ff', '#6941c6', { fs: 10, fw: 600 }) : '';
          var availEl = m.available ? tag('Disponible', '#ecfdf3', '#067647', { pill: true, dot: true, fs: 11, fw: 500 }) : tag('Indispo.', '#fef3f2', '#b42318', { pill: true, dot: true, fs: 11, fw: 500 });
          var actStyle = 'padding:5px 12px;border-radius:7px;font-size:12px;font-weight:600;cursor:' + (m.is_active ? 'default' : 'pointer') + ';display:inline-flex;align-items:center;border:' + (m.is_active ? '1px solid #abefc6' : '1px solid #7f56d9') + ';background:' + (m.is_active ? '#ecfdf3' : '#7f56d9') + ';color:' + (m.is_active ? '#067647' : '#fff') + ';';
          return '<div style="display:grid;grid-template-columns:1fr 150px 110px 100px 160px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border-tertiary);"><div><div style="display:flex;align-items:center;gap:8px;"><span style="font-size:13.5px;font-weight:600;color:var(--text-secondary);">' + esc(m.label) + '</span>' + activeEl + '</div><div style="font-size:11.5px;color:var(--text-quaternary);margin-top:1px;">' + esc(KIND_LABEL[m.kind] || m.kind) + '</div></div><div style="font-size:12.5px;color:var(--text-tertiary);">' + esc(KIND_LABEL[m.kind] || m.kind) + '</div><div>' + availEl + '</div><div style="font-family:' + MONO + ';font-size:12.5px;color:var(--text-secondary);">' + f1 + '</div><div style="display:flex;gap:6px;justify-content:flex-end;"><span data-click="modelActivate" data-arg="' + m.id + '" style="' + actStyle + '">' + (m.is_active ? 'Actif' : 'Activer') + '</span><span data-click="modelRescan" data-arg="' + m.id + '" style="padding:5px 10px;border:1px solid var(--border-primary);border-radius:7px;font-size:12px;font-weight:600;color:var(--text-secondary);cursor:pointer;display:inline-flex;align-items:center;gap:5px;"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"/><path d="M3.5 9a9 9 0 0 1 14.8-3.4L23 10"/></svg>Re-scanner</span></div></div>';
        }).join('');
        body = '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;background:#fff;"><div class="scrl" style="overflow-x:auto;"><div style="min-width:760px;"><div style="display:grid;grid-template-columns:1fr 150px 110px 100px 160px;background:var(--gray-50);border-bottom:1px solid var(--border-primary);padding:9px 16px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--text-quaternary);"><div>Moteur</div><div>Type</div><div>Disponible</div><div>F1 niv.1</div><div style="text-align:right;">Actions</div></div>' + mrows + '</div></div></div>';
      }
    } else if (at === 'ops') {
      if (!state.ops) body = loadingPanel('Chargement…');
      else {
        var o = state.ops, used = o.disk.total_bytes - o.disk.free_bytes, pctDisk = o.disk.total_bytes ? Math.round(used / o.disk.total_bytes * 100) : 0;
        body = '<div style="display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;background:#fff;"><div style="padding:18px;border-right:1px solid var(--border-secondary);"><div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:8px;">Lots traités</div><div style="font-size:26px;font-weight:600;font-family:' + MONO + ';">' + fmt(o.batches.total) + '</div><div style="font-size:11.5px;color:var(--text-quaternary);margin-top:4px;">depuis le lancement</div></div><div style="padding:18px;border-right:1px solid var(--border-secondary);"><div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:8px;">Taux d\'échec</div><div style="font-size:26px;font-weight:600;font-family:' + MONO + ';color:var(--warning-700);">' + pct1(o.batches.failure_rate * 100) + '</div><div style="font-size:11.5px;color:var(--text-quaternary);margin-top:4px;">' + (o.batches.by_status.failed || 0) + ' lots en échec</div></div><div style="padding:18px;border-right:1px solid var(--border-secondary);"><div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:8px;">Durée moyenne</div><div style="font-size:26px;font-weight:600;font-family:' + MONO + ';">' + fmtDuration(o.batches.avg_duration_s) + '</div><div style="font-size:11.5px;color:var(--text-quaternary);margin-top:4px;">par lot terminé</div></div><div style="padding:18px;"><div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-quaternary);margin-bottom:8px;">Espace disque</div><div style="font-size:26px;font-weight:600;font-family:' + MONO + ';">' + go1(used) + '<span style="font-size:15px;color:var(--text-quaternary);"> / ' + go1(o.disk.total_bytes) + ' Go</span></div><div style="height:6px;background:var(--gray-100);border-radius:9999px;margin-top:8px;overflow:hidden;"><div style="width:' + pctDisk + '%;height:100%;background:var(--brand-500);border-radius:9999px;"></div></div></div></div>';
      }
    } else if (at === 'retention') {
      body = '<div style="border:1px solid #fecdca;border-radius:8px;background:#fffbfa;padding:22px;max-width:640px;"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;"><span style="width:34px;height:34px;border-radius:8px;background:#fef3f2;color:#b42318;display:grid;place-items:center;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></span><div><div style="font-size:15px;font-weight:600;color:var(--error-700);">Purge RGPD</div><div style="font-size:12.5px;color:var(--text-tertiary);">Action irréversible</div></div></div><div style="font-size:13.5px;color:var(--text-secondary);line-height:1.5;margin-bottom:16px;">Supprime définitivement tous les lots et verbatims dont la date dépasse la durée de rétention (<span style="font-family:' + MONO + ';font-weight:600;">' + esc(String(state.cfgRetention)) + ' mois</span>). Cette opération ne peut pas être annulée et sera consignée dans le journal d\'audit.</div><button data-click="purge" class="h-purge" style="height:40px;padding:0 18px;background:var(--error-600);color:#fff;border:none;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;">Purger les données expirées</button></div>';
    } else {
      if (!state.audit) body = loadingPanel('Chargement du journal…');
      else {
        var arows = state.audit.map(function (a) { return '<div style="display:grid;grid-template-columns:170px 130px 170px 130px 1fr;align-items:center;padding:10px 16px;border-bottom:1px solid var(--border-tertiary);font-size:12.5px;"><div style="font-family:' + MONO + ';color:var(--text-quaternary);">' + esc(fmtDateTime(a.created_at)) + '</div><div style="font-family:' + MONO + ';color:var(--text-tertiary);">' + esc(a.user || '—') + '</div><div style="color:var(--text-secondary);font-weight:500;">' + esc(a.action) + '</div><div style="font-family:' + MONO + ';color:var(--text-tertiary);">' + esc((a.entity_id || a.entity || '—')) + '</div><div style="color:var(--text-tertiary);">' + esc(a.details || '') + '</div></div>'; }).join('');
        body = '<div style="border:1px solid var(--border-primary);border-radius:8px;overflow:hidden;background:#fff;"><div class="scrl" style="overflow-x:auto;"><div style="min-width:840px;"><div style="display:grid;grid-template-columns:170px 130px 170px 130px 1fr;background:var(--gray-50);border-bottom:1px solid var(--border-primary);padding:9px 16px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--text-quaternary);"><div>Date</div><div>Utilisateur</div><div>Action</div><div>Cible</div><div>Détails</div></div>' + arows + '</div></div></div>';
      }
    }
    return wrap('<div style="margin-bottom:16px;"><div style="font-size:19px;font-weight:600;">Administration</div><div style="font-size:13.5px;color:var(--text-tertiary);margin-top:2px;">Configuration, moteurs, exploitation, conformité RGPD et audit.</div></div>' + tabs + body, 1100);
  }
  function fmtDateTime(iso) { if (!iso) return '—'; var d = new Date(iso); if (isNaN(d.getTime())) return iso; var p = function (n) { return (n < 10 ? '0' : '') + n; }; return p(d.getDate()) + '/' + p(d.getMonth() + 1) + '/' + d.getFullYear() + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()); }

  /* ================================================================ COMPTE */
  function account() {
    var pwT = state.pwMsg ? state.pwMsg.split(':')[0] : '', pwTxt = state.pwMsg ? state.pwMsg.slice(state.pwMsg.indexOf(':') + 1) : '';
    var msg = state.pwMsg ? '<div style="font-size:13px;padding:9px 12px;border-radius:8px;margin-bottom:16px;background:' + (pwT === 'ok' ? '#ecfdf3' : '#fef3f2') + ';color:' + (pwT === 'ok' ? '#067647' : '#b42318') + ';border:1px solid ' + (pwT === 'ok' ? '#abefc6' : '#fecdca') + ';">' + esc(pwTxt) + '</div>' : '';
    var uname = (state.me && state.me.username) || '—', role = isAdmin() ? 'Admin' : 'Analyste';
    return wrap('<div style="margin-bottom:18px;"><div style="font-size:19px;font-weight:600;">Mon compte</div><div style="font-size:13.5px;color:var(--text-tertiary);margin-top:2px;">' + esc(uname) + ' · <span style="font-family:' + MONO + ';">' + esc(uname) + '</span> · ' + role + '</div></div><div style="border:1px solid var(--border-primary);border-radius:8px;background:#fff;padding:22px;"><div style="font-size:14px;font-weight:600;margin-bottom:16px;">Changer le mot de passe</div><div style="font-size:12.5px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Mot de passe actuel</div><input data-f="pwOld" data-input="pwOld" type="password" value="' + esc(state.pwOld) + '" style="width:100%;height:40px;padding:0 12px;border:1px solid var(--border-primary);border-radius:8px;font-size:14px;margin-bottom:14px;box-shadow:var(--shadow-xs);" /><div style="font-size:12.5px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Nouveau mot de passe</div><input data-f="pwNew" data-input="pwNew" type="password" value="' + esc(state.pwNew) + '" placeholder="12 caractères minimum" style="width:100%;height:40px;padding:0 12px;border:1px solid var(--border-primary);border-radius:8px;font-size:14px;margin-bottom:14px;box-shadow:var(--shadow-xs);" /><div style="font-size:12.5px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Confirmer le nouveau mot de passe</div><input data-f="pwConf" data-input="pwConf" type="password" value="' + esc(state.pwConf) + '" style="width:100%;height:40px;padding:0 12px;border:1px solid var(--border-primary);border-radius:8px;font-size:14px;margin-bottom:16px;box-shadow:var(--shadow-xs);" />' + msg + '<button data-click="changePw" class="h-brand" style="height:40px;padding:0 18px;background:var(--brand-600);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;">Mettre à jour</button></div>', 520);
  }

  /* ================================================================ RENDU */
  function content() {
    if (state.error && ['lots', 'accueil', 'dashboards', 'users', 'admin'].indexOf(state.route) >= 0 && !state.batches && !state.users) return wrap(errorPanel(state.error));
    switch (state.route) {
      case 'accueil': return home();
      case 'lots': return lots();
      case 'new': return newBatch();
      case 'detail': return detail();
      case 'dashboards': return dashboards();
      case 'test': return testScreen();
      case 'help': return help();
      case 'users': return users();
      case 'admin': return admin();
      case 'account': return account();
      default: return '';
    }
  }
  function appShell() {
    return '<div style="height:100vh;display:flex;">' + aside() + '<div style="flex:1;display:flex;flex-direction:column;min-width:0;">' + topbar() + '<main class="scrl" style="flex:1;overflow-y:auto;padding:24px 28px;">' + content() + '</main></div>' + toast() + '</div>';
  }
  function bootScreen() {
    return '<div style="height:100vh;display:flex;align-items:center;justify-content:center;background:var(--gray-50);"><span style="width:22px;height:22px;border:3px solid #e4e7ec;border-top-color:#7f56d9;border-radius:50%;animation:spin .7s linear infinite;display:inline-block;"></span></div>';
  }
  function captureFocus() { var a = document.activeElement; if (a && a.getAttribute && a.getAttribute('data-f')) { var c = { f: a.getAttribute('data-f') }; try { c.s = a.selectionStart; c.e = a.selectionEnd; } catch (e) { } return c; } return null; }
  function restoreFocus(c) { if (!c) return; var el = root.querySelector('[data-f="' + c.f + '"]'); if (el) { el.focus(); try { if (c.s != null) el.setSelectionRange(c.s, c.e); } catch (e) { } } }
  function render() {
    var cap = captureFocus();
    root.innerHTML = state.booting ? bootScreen() : (state.authed ? appShell() : loginScreen());
    restoreFocus(cap);
  }
  function setState(patch) { Object.assign(state, patch); render(); }
  function setQuiet(patch) { Object.assign(state, patch); }
  function flash(msg) { setState({ toast: msg }); clearTimeout(toastTimer); toastTimer = setTimeout(function () { setState({ toast: '' }); }, 2400); }

  /* ================================================================ CHARGEURS */
  async function loadCommon() {
    try { if (!state.meta) state.meta = await API.getMeta(); } catch (e) { }
    try { if (!state.modelKpi) state.modelKpi = await API.getModelKpi(); } catch (e) { }
  }
  async function loadRoute(route) {
    state.error = '';
    try {
      if (route === 'accueil') { await loadCommon(); var r = await Promise.all([API.listBatches(), API.getVolumetry().catch(function () { return { series: [], total_verbatims: 0, n_batches: 0, global_themes: {}, theme_sentiment: {} }; })]); state.batches = r[0]; state.volumetry = r[1]; }
      else if (route === 'lots') { state.batches = await API.listBatches(); }
      else if (route === 'dashboards') { await loadCommon(); state.volumetry = await API.getVolumetry(); }
      else if (route === 'users') { state.users = await API.listUsers(); }
      else if (route === 'detail') { await loadDetail(); }
      else if (route === 'admin') { await loadAdminTab(state.adminTab); if (!state.config) { try { var c = await API.getConfig(); applyConfig(c); } catch (e) { } } }
      render();
    } catch (e) { setState({ error: e.message || String(e) }); }
  }
  function applyConfig(c) { state.config = c; state.cfgRetention = parseInt(c.retention_months, 10) || 12; state.cfgSeuil = parseFloat(c.default_seuil_revue) || 0.5; }
  async function loadAdminTab(tab) {
    if (!isAdmin()) { state.error = 'Réservé aux administrateurs.'; return; }
    if (tab === 'config') { var c = await API.getConfig(); applyConfig(c); }
    else if (tab === 'models') { state.models = await API.listModels(); }
    else if (tab === 'ops') { state.ops = await API.getOps(); }
    else if (tab === 'audit') { state.audit = await API.getAudit(100); }
    else if (tab === 'retention') { if (!state.config) { try { applyConfig(await API.getConfig()); } catch (e) { } } }
  }
  async function loadDetail() {
    state.detailLoading = true; render();
    try {
      var r = await Promise.all([
        API.getBatch(state.detailBatch),
        API.getBatchKpi(state.detailBatch).catch(function () { return null; }),
        API.getReviewQueue(state.detailBatch, 0, 500).catch(function () { return { total: 0, items: [] }; })
      ]);
      state.detailObj = r[0]; state.detailKpi = r[1]; state.reviewQueue = r[2]; state.revIdx = 0; state.revForm = null;
      if (!state.taxonomy) { try { state.taxonomy = await API.getTaxonomy(); } catch (e) { state.taxonomy = { themes: [] }; } }
      state.detailLoading = false; render();
      if (state.detailTab === 'results') await loadResults();
    } catch (e) { state.detailLoading = false; setState({ error: e.message || String(e) }); }
  }
  function currentFilters() {
    var f = { q: state.fText || undefined, niv1: state.fTheme || undefined, limit: 50, offset: state.resultsOffset };
    if (state.fSent) f.sentiment = SENT_REV[state.fSent];
    if (state.fSignal === 'RUP') f.rupture = true; else if (state.fSignal === 'CHU') f.churn = true; else if (state.fSignal === 'INS') f.insatisfaction = true;
    if (state.fStatus === 'revue') f.revue = true; else if (state.fStatus === 'auto') f.revue = false;
    return f;
  }
  async function loadResults() {
    state.resultsLoading = true; render();
    try { state.results = await API.listResults(state.detailBatch, currentFilters()); state.resultsLoading = false; render(); }
    catch (e) { state.resultsLoading = false; setState({ error: e.message || String(e) }); }
  }
  function reloadResultsDebounced() { clearTimeout(filterTimer); filterTimer = setTimeout(function () { state.resultsOffset = 0; loadResults(); }, 250); }

  async function loadReviewQueue() {
    try { state.reviewQueue = await API.getReviewQueue(state.detailBatch, 0, 500); state.revIdx = 0; state.revForm = null; render(); } catch (e) { }
  }

  /* ================================================================ ACTIONS */
  async function doLogin() {
    if (state.loginBusy) return;
    if (!state.loginId.trim() || !state.loginPw.trim()) { setState({ loginError: 'Identifiant et mot de passe requis.' }); return; }
    setState({ loginBusy: true, loginError: '' });
    try {
      var me = await API.login(state.loginId.trim(), state.loginPw);
      state.me = me; state.authed = true; state.loginBusy = false; state.loginPw = ''; state.route = 'accueil';
      render(); loadRoute('accueil');
    } catch (e) {
      setState({ loginBusy: false, loginError: e.status === 429 ? e.message : 'Identifiant ou mot de passe incorrect.' });
    }
  }
  async function doLogout() {
    try { await API.logout(); } catch (e) { }
    setState({ authed: false, me: null, loginId: '', loginPw: '', loginError: '', route: 'accueil', batches: null, volumetry: null, users: null, models: null, audit: null, ops: null, detailObj: null });
  }
  function openBatch(id) { state.detailBatch = id; state.detailTab = 'dashboard'; setState({ route: 'detail' }); loadDetail(); }

  function pickFile(which) {
    if (API.isDemo()) {
      if (which === 'mdtc') setState({ nbMDTC: { name: 'MDTC_mai2026.xlsx', size: '2,4 Mo' } });
      else setState({ nbMopinion: { name: 'Mopinion_mai2026.xlsx', size: '1,8 Mo' } });
    } else {
      var el = document.getElementById(which === 'mdtc' ? 'fileMDTC' : 'fileMopinion'); if (el) el.click();
    }
  }
  function onFile(which, file) {
    if (!file) return;
    var o = {}; o[which === 'mdtc' ? 'nbMDTC' : 'nbMopinion'] = { name: file.name, size: humanSize(file.size), file: file };
    setState(o);
  }
  function cancelTimers() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
  function patchProgress() {
    var bar = document.getElementById('nbBar'); if (bar) bar.style.width = state.nbProgress + '%';
    var step = document.getElementById('nbStep'); if (step) step.textContent = stepText();
    var pct = document.getElementById('nbPct'); if (pct) pct.textContent = Math.round(state.nbProgress) + ' %';
  }
  async function launchBatch() {
    if (!state.nbMDTC && !state.nbMopinion) return;
    cancelTimers();
    setState({ nbRunning: true, nbProgress: 0, nbDone: false, nbError: '' });
    try {
      var batch = await API.createBatch({ label: state.nbLabel || undefined, seuilRevue: state.nbSeuil, mdtc: state.nbMDTC && state.nbMDTC.file, mopinion: state.nbMopinion && state.nbMopinion.file });
      state.nbBatchId = batch.id; render();
      pollTimer = setInterval(pollProgress, 800);
    } catch (e) { setState({ nbRunning: false, nbError: e.message || 'Lancement impossible.' }); }
  }
  async function pollProgress() {
    try {
      var p = await API.getBatchProgress(state.nbBatchId);
      state.nbProgress = Math.round((p.progress || 0) * 100); patchProgress();
      if (p.status === 'done') { cancelTimers(); setState({ nbRunning: false, nbDone: true }); }
      else if (p.status === 'failed' || p.status === 'canceled') { cancelTimers(); setState({ nbRunning: false, nbError: 'Traitement ' + (p.status === 'failed' ? 'en échec.' : 'annulé.') }); }
    } catch (e) { cancelTimers(); setState({ nbRunning: false, nbError: e.message || 'Suivi interrompu.' }); }
  }
  async function cancelBatch() {
    cancelTimers();
    if (state.nbBatchId != null) { try { await API.cancelBatch(state.nbBatchId); } catch (e) { } }
    setState({ nbRunning: false, nbProgress: 0 });
  }
  function resetBatch() { cancelTimers(); setState({ nbLabel: '', nbMDTC: null, nbMopinion: null, nbRunning: false, nbProgress: 0, nbDone: false, nbError: '', nbBatchId: null, nbSeuil: 0.5 }); }

  function revCurrent() { var items = (state.reviewQueue && state.reviewQueue.items || []).map(mapResult); return items[Math.min(state.revIdx, Math.max(0, items.length - 1))]; }
  function revSet(field, val) {
    if (!state.revForm) return;
    state.revForm[field] = val;
    if (field === 't1') state.revForm.t2 = (themesMap()[val] || [])[0] || '';
    render();
  }
  function revToggleSig(code) {
    if (!state.revForm) return;
    var i = state.revForm.sig.indexOf(code);
    if (i >= 0) state.revForm.sig.splice(i, 1); else state.revForm.sig.push(code);
    render();
  }
  async function revValidate() {
    var cur = revCurrent(); if (!cur || !state.revForm) return;
    var rf = state.revForm;
    var payload = { action: 'correct', theme1_niv1: rf.t1, theme1_niv2: rf.t2, theme1_sentiment: SENT_REV[rf.sent], signal_rupture: rf.sig.indexOf('RUP') >= 0, signal_churn: rf.sig.indexOf('CHU') >= 0, signal_insatisfaction: rf.sig.indexOf('INS') >= 0 };
    try { await API.correctResult(cur.id, payload); flash('Verbatim #' + cur.id + ' corrigé et validé.'); await loadReviewQueue(); }
    catch (e) { flash('Erreur : ' + (e.message || 'correction refusée.')); }
  }

  async function runTest() {
    var txt = state.testText.trim(); if (!txt) return;
    setState({ testLoading: true, testRes: null });
    try { var res = await API.predict(txt, state.testNote ? parseInt(state.testNote, 10) : null); setState({ testLoading: false, testRes: res }); }
    catch (e) { setState({ testLoading: false }); flash('Analyse impossible : ' + (e.message || '')); }
  }
  async function changePw() {
    var s = state;
    if (!s.pwOld || !s.pwNew || !s.pwConf) { setState({ pwMsg: 'err:Tous les champs sont requis.' }); return; }
    if (s.pwNew.length < 12) { setState({ pwMsg: 'err:Le nouveau mot de passe doit faire au moins 12 caractères.' }); return; }
    if (s.pwNew !== s.pwConf) { setState({ pwMsg: 'err:La confirmation ne correspond pas.' }); return; }
    try { await API.changePassword(s.pwOld, s.pwNew); setState({ pwMsg: 'ok:Mot de passe mis à jour.', pwOld: '', pwNew: '', pwConf: '' }); }
    catch (e) { setState({ pwMsg: 'err:' + (e.message || 'Échec de la mise à jour.') }); }
  }

  /* ================================================================ DISPATCH */
  async function dispatch(act, value, e) {
    switch (act) {
      case 'loginId': setQuiet({ loginId: value }); break;
      case 'loginPw': setQuiet({ loginPw: value }); break;
      case 'loginKey': if (value === 'Enter') doLogin(); break;
      case 'doLogin': doLogin(); break;
      case 'go': state.route = value; if (value === 'new') { } setState({ route: value, error: '' }); loadRoute(value); break;
      case 'logout': if (e && e.stopPropagation) e.stopPropagation(); doLogout(); break;
      case 'account': setState({ route: 'account' }); break;
      case 'openBatch': openBatch(value); break;

      case 'pickMDTC': pickFile('mdtc'); break;
      case 'pickMopinion': pickFile('mopinion'); break;
      case 'fileMDTC': onFile('mdtc', value); break;
      case 'fileMopinion': onFile('mopinion', value); break;
      case 'nbLabel': setQuiet({ nbLabel: value }); break;
      case 'nbSeuil': { state.nbSeuil = parseFloat(value); var l = document.getElementById('nbSeuilLabel'); if (l) l.textContent = dec(state.nbSeuil); break; }
      case 'launch': launchBatch(); break;
      case 'cancel': cancelBatch(); break;
      case 'resetNb': resetBatch(); break;

      case 'detailTab': state.detailTab = value; state.error = ''; render(); if (value === 'results') { state.resultsOffset = 0; loadResults(); } else if (value === 'review') loadReviewQueue(); break;

      case 'fText': setQuiet({ fText: value }); reloadResultsDebounced(); break;
      case 'fTheme': setQuiet({ fTheme: value }); reloadResultsDebounced(); break;
      case 'fSent': state.fSent = value; state.resultsOffset = 0; loadResults(); break;
      case 'fSignal': state.fSignal = value; state.resultsOffset = 0; loadResults(); break;
      case 'fStatus': state.fStatus = value; state.resultsOffset = 0; loadResults(); break;
      case 'resPrev': if (state.results && state.results.offset > 0) { state.resultsOffset = Math.max(0, state.results.offset - state.results.limit); loadResults(); } break;
      case 'resNext': if (state.results && state.results.offset + state.results.limit < state.results.total) { state.resultsOffset = state.results.offset + state.results.limit; loadResults(); } break;
      case 'exportCSV': triggerExport(API.exportUrl(state.detailBatch, 'csv'), 'CSV'); break;
      case 'exportXLSX': triggerExport(API.exportUrl(state.detailBatch, 'xlsx'), 'XLSX'); break;

      case 'revGo': setState({ revIdx: parseInt(value, 10), revForm: null }); break;
      case 'revT1': revSet('t1', value); break;
      case 'revT2': revSet('t2', value); break;
      case 'revSent': revSet('sent', value); break;
      case 'revSig': revToggleSig(value); break;
      case 'revValidate': revValidate(); break;
      case 'exportCorr': triggerExport(API.exportCorrectionsUrl(), 'corrections'); break;

      case 'testText': setQuiet({ testText: value }); break;
      case 'testNote': setQuiet({ testNote: value }); break;
      case 'runTest': runTest(); break;

      case 'createUser': flash('Création de compte — à brancher (POST /api/users).'); break;
      case 'userToggle': await toggleUser(parseInt(value, 10)); break;

      case 'adminTab': state.adminTab = value; render(); loadAdminTab(value).then(render).catch(function (er) { setState({ error: er.message }); }); break;
      case 'cfgRetention': setQuiet({ cfgRetention: value }); break;
      case 'cfgSeuil': { state.cfgSeuil = parseFloat(value); var l2 = document.getElementById('cfgSeuilLabel'); if (l2) l2.textContent = dec(state.cfgSeuil); break; }
      case 'saveCfg': await saveCfg(); break;
      case 'purge': await doPurge(); break;
      case 'modelActivate': await activateModel(parseInt(value, 10)); break;
      case 'modelRescan': await rescanModels(); break;

      case 'pwOld': setQuiet({ pwOld: value }); break;
      case 'pwNew': setQuiet({ pwNew: value }); break;
      case 'pwConf': setQuiet({ pwConf: value }); break;
      case 'changePw': changePw(); break;
    }
  }
  function triggerExport(url, label) {
    if (API.isDemo()) { flash('Export ' + label + ' (démo — non généré).'); return; }
    var a = document.createElement('a'); a.href = url; a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove();
    flash('Export ' + label + ' lancé.');
  }
  async function toggleUser(id) {
    var u = (state.users || []).filter(function (x) { return x.id === id; })[0]; if (!u) return;
    try { if (u.is_active) await API.deactivateUser(id); else await API.updateUser(id, { is_active: true }); flash((u.is_active ? 'Compte désactivé : ' : 'Compte activé : ') + u.username); state.users = await API.listUsers(); render(); }
    catch (e) { flash('Erreur : ' + (e.message || '')); }
  }
  async function saveCfg() {
    try { var c = await API.patchConfig({ retention_months: parseInt(state.cfgRetention, 10), default_seuil_revue: state.cfgSeuil }); applyConfig(c); flash('Configuration enregistrée.'); }
    catch (e) { flash('Erreur : ' + (e.message || '')); }
  }
  async function doPurge() {
    try { var r = await API.purge(); flash('Purge RGPD exécutée — ' + (r.batches || 0) + ' lot(s) supprimé(s).'); }
    catch (e) { flash('Erreur : ' + (e.message || '')); }
  }
  async function activateModel(id) {
    var m = (state.models || []).filter(function (x) { return x.id === id; })[0]; if (!m || m.is_active) return;
    try { await API.activateModel(id); flash('Moteur « ' + m.label + ' » activé.'); state.models = await API.listModels(); try { state.meta = await API.getMeta(); state.modelKpi = await API.getModelKpi(); } catch (e) { } render(); }
    catch (e) { flash('Erreur : ' + (e.message || '')); }
  }
  async function rescanModels() {
    try { await API.rescanModels(); flash('Re-scan des moteurs lancé.'); state.models = await API.listModels(); render(); }
    catch (e) { flash('Erreur : ' + (e.message || '')); }
  }

  /* ================================================================ ÉVÈNEMENTS */
  root.addEventListener('click', function (e) { var el = e.target.closest('[data-click]'); if (!el) return; dispatch(el.getAttribute('data-click'), el.getAttribute('data-arg'), e); });
  root.addEventListener('input', function (e) { var el = e.target.closest('[data-input]'); if (!el) return; dispatch(el.getAttribute('data-input'), el.value, e); });
  root.addEventListener('change', function (e) { var el = e.target.closest('[data-change]'); if (!el) return; if (el.type === 'file') { dispatch(el.getAttribute('data-change'), el.files && el.files[0], e); return; } dispatch(el.getAttribute('data-change'), el.value, e); });
  root.addEventListener('keydown', function (e) { var el = e.target.closest('[data-keydown]'); if (!el) return; dispatch(el.getAttribute('data-keydown'), e.key, e); });

  /* ================================================================ BOOT */
  (async function boot() {
    render();
    if (API.isDemo()) { setState({ booting: false, authed: false }); return; }
    try { var me = await API.me(); state.me = me; state.authed = true; state.booting = false; render(); loadRoute('accueil'); }
    catch (e) { setState({ booting: false, authed: false }); }
  })();
})();
