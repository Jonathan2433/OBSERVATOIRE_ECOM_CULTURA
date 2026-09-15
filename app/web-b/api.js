/* =====================================================================
   OBSERVATOIRE ECOM STUDIO — Direction B · couche API
   ---------------------------------------------------------------------
   Client fidèle de l'API FastAPI (cf. app/web/src/api.ts). Toutes les
   méthodes renvoient les *formes brutes* de l'API ; le mapping vers les
   vues est fait dans app.js.

   Deux modes, derrière la MÊME interface `window.API` :
     • LIVE  — `fetch('/api/...')`, cookie de session (credentials:include).
               Actif dès que la page est servie en http(s) (conteneur web).
     • DEMO  — fixtures en mémoire (mêmes formes que l'API), pour aperçu
               hors back-end : ouverture en `file://` ou `?demo=1`.
   ===================================================================== */
(function () {
  'use strict';

  var DEMO = (location.protocol === 'file:') || /[?&]demo=1\b/.test(location.search);
  var FORCE_LIVE = /[?&]live=1\b/.test(location.search);
  if (FORCE_LIVE) DEMO = false;

  /* ------------------------------------------------------------------ */
  /*  LIVE — fetch helpers                                              */
  /* ------------------------------------------------------------------ */
  function ApiError(status, message) { this.name = 'ApiError'; this.status = status; this.message = message; }
  ApiError.prototype = Object.create(Error.prototype);

  async function req(url, options) {
    options = options || {};
    var headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    var res = await fetch(url, Object.assign({ credentials: 'include', headers: headers }, options));
    if (!res.ok) {
      var detail = 'Erreur ' + res.status;
      try { var b = await res.json(); if (b && b.detail) detail = typeof b.detail === 'string' ? b.detail : JSON.stringify(b.detail); } catch (e) { }
      throw new ApiError(res.status, detail);
    }
    if (res.status === 204) return undefined;
    return res.json();
  }
  function qs(params) {
    var p = new URLSearchParams();
    Object.keys(params).forEach(function (k) { var v = params[k]; if (v !== undefined && v !== null && v !== '') p.set(k, v); });
    var s = p.toString();
    return s ? ('?' + s) : '';
  }

  var live = {
    health: function () { return req('/api/health'); },
    login: function (username, password) { return req('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: username, password: password }) }); },
    logout: function () { return req('/api/auth/logout', { method: 'POST' }); },
    me: function () { return req('/api/auth/me'); },
    changePassword: function (cur, neu) { return req('/api/auth/password', { method: 'POST', body: JSON.stringify({ current_password: cur, new_password: neu }) }); },

    listUsers: function () { return req('/api/users'); },
    createUser: function (username, password, role) { return req('/api/users', { method: 'POST', body: JSON.stringify({ username: username, password: password, role: role }) }); },
    updateUser: function (id, patch) { return req('/api/users/' + id, { method: 'PATCH', body: JSON.stringify(patch) }); },
    deactivateUser: function (id) { return req('/api/users/' + id, { method: 'DELETE' }); },

    listBatches: function () { return req('/api/batches'); },
    getBatch: function (id) { return req('/api/batches/' + id); },
    getBatchProgress: function (id) { return req('/api/batches/' + id + '/progress'); },
    cancelBatch: function (id) { return req('/api/batches/' + id + '/cancel', { method: 'POST' }); },
    createBatch: function (opts) {
      var form = new FormData();
      if (opts.label) form.append('label', opts.label);
      form.append('seuil_revue', String(opts.seuilRevue));
      if (opts.mdtc) form.append('mdtc', opts.mdtc);
      if (opts.mopinion) form.append('mopinion', opts.mopinion);
      return fetch('/api/batches', { method: 'POST', credentials: 'include', body: form }).then(async function (res) {
        if (!res.ok) { var d = 'Erreur ' + res.status; try { var b = await res.json(); if (b && b.detail) d = typeof b.detail === 'string' ? b.detail : JSON.stringify(b.detail); } catch (e) { } throw new ApiError(res.status, d); }
        return res.json();
      });
    },

    listResults: function (batchId, f) {
      f = f || {};
      return req('/api/batches/' + batchId + '/results' + qs({
        niv1: f.niv1, sentiment: f.sentiment, revue: f.revue === undefined ? undefined : String(f.revue),
        rupture: f.rupture ? 'true' : undefined, churn: f.churn ? 'true' : undefined, insatisfaction: f.insatisfaction ? 'true' : undefined,
        q: f.q, limit: f.limit == null ? 50 : f.limit, offset: f.offset || 0
      }));
    },
    exportUrl: function (batchId, format) { return '/api/batches/' + batchId + '/export?format=' + format; },
    exportCorrectionsUrl: function () { return '/api/corrections/export'; },
    getReviewQueue: function (batchId, offset, limit) { return req('/api/batches/' + batchId + '/review' + qs({ limit: limit == null ? 50 : limit, offset: offset || 0 })); },
    correctResult: function (id, payload) { return req('/api/results/' + id, { method: 'PATCH', body: JSON.stringify(payload) }); },
    getTaxonomy: function () { return req('/api/taxonomy'); },

    getBatchKpi: function (id) { return req('/api/batches/' + id + '/kpi'); },
    getVolumetry: function () { return req('/api/kpi/volumetry'); },
    getModelKpi: function () { return req('/api/kpi/model'); },

    listModels: function () { return req('/api/models'); },
    activateModel: function (id) { return req('/api/models/' + id + '/activate', { method: 'POST' }); },
    rescanModels: function () { return req('/api/models/rescan', { method: 'POST' }); },

    getAudit: function (limit) { return req('/api/audit' + qs({ limit: limit == null ? 100 : limit })); },
    getConfig: function () { return req('/api/config'); },
    patchConfig: function (p) { return req('/api/config', { method: 'PATCH', body: JSON.stringify(p) }); },
    purge: function () { return req('/api/admin/purge', { method: 'POST' }); },
    getOps: function () { return req('/api/admin/ops'); },

    getMeta: function () { return req('/api/meta'); },
    predict: function (text, satisfaction) { return req('/api/predict', { method: 'POST', body: JSON.stringify({ text: text, satisfaction: satisfaction == null ? null : satisfaction }) }); }
  };

  /* ------------------------------------------------------------------ */
  /*  DEMO — fixtures (mêmes formes que l'API)                          */
  /* ------------------------------------------------------------------ */
  var D = (function () {
    var THEMES = {
      'Livraison': ['Retard', 'Colis perdu', 'Livreur', 'Frais de port'],
      'Produit': ['Qualité', 'Conformité', 'Disponibilité', 'Notice'],
      'Site web': ['Navigation', 'Bug', 'Performance', 'Compte'],
      'Paiement': ['Échec paiement', 'Remboursement', 'Facturation'],
      'Relation client': ['Conseil', 'SAV', 'Amabilité', 'Délai de réponse'],
      'Magasin': ['Accueil', 'Propreté', 'File d’attente', 'Stock'],
      'Commande': ['Annulation', 'Modification', 'Erreur de préparation'],
      'Prix': ['Promotion', 'Tarif', 'Fidélité']
    };
    // [src, text, niv1, niv2, sentiment, [signaux], conf, statut]
    var rawV = [
      ['MDTC', 'Commande [COMMANDE] jamais reçue, le support reste injoignable depuis 10 jours.', 'Livraison', 'Retard', 'Négatif', ['RUP'], 0.93, 'auto'],
      ['MDTC', 'Article défectueux dès l’ouverture, je demande un remboursement sur [EMAIL].', 'Produit', 'Qualité', 'Négatif', ['INS'], 0.47, 'revue'],
      ['Mopinion', 'Très bon conseil en magasin, [NOM] a été parfait, merci.', 'Relation client', 'Conseil', 'Positif', [], 0.88, 'corrige'],
      ['Mopinion', 'Le site rame au moment de payer, j’ai dû recommencer trois fois.', 'Site web', 'Performance', 'Négatif', [], 0.71, 'auto'],
      ['MDTC', 'Colis livré à la mauvaise adresse, transporteur introuvable au [TEL].', 'Livraison', 'Colis perdu', 'Négatif', ['RUP', 'INS'], 0.84, 'auto'],
      ['Mopinion', 'Je ne commanderai plus jamais ici après cette expérience.', 'Relation client', 'SAV', 'Négatif', ['CHU', 'INS'], 0.43, 'revue'],
      ['MDTC', 'Produit conforme et livraison rapide, rien à redire.', 'Produit', 'Conformité', 'Positif', [], 0.91, 'auto'],
      ['Mopinion', 'Impossible de me connecter à mon compte [EMAIL], mot de passe refusé.', 'Site web', 'Compte', 'Neutre', [], 0.66, 'auto'],
      ['MDTC', 'Remboursement promis sous 14 jours, toujours rien après un mois.', 'Paiement', 'Remboursement', 'Négatif', ['CHU'], 0.38, 'revue'],
      ['Mopinion', 'Magasin propre et personnel souriant, bonne expérience.', 'Magasin', 'Accueil', 'Positif', [], 0.86, 'auto'],
      ['MDTC', 'Tarif affiché différent du tarif en caisse, je me sens floué.', 'Prix', 'Tarif', 'Négatif', ['INS'], 0.49, 'revue'],
      ['Mopinion', 'Notice incompréhensible, produit renvoyé aussitôt.', 'Produit', 'Notice', 'Négatif', [], 0.74, 'auto'],
      ['MDTC', 'Commande annulée sans explication, [NOM] n’a pas su m’aider.', 'Commande', 'Annulation', 'Négatif', ['INS'], 0.29, 'revue'],
      ['Mopinion', 'Livreur très aimable, créneau parfaitement respecté.', 'Livraison', 'Livreur', 'Positif', [], 0.90, 'auto'],
      ['Mopinion', 'File d’attente interminable en caisse un samedi après-midi.', 'Magasin', 'File d’attente', 'Négatif', [], 0.69, 'auto'],
      ['MDTC', 'Rupture de stock sur tout le rayon, déplacement pour rien.', 'Magasin', 'Stock', 'Négatif', ['CHU'], 0.41, 'revue']
    ];
    var results = rawV.map(function (r, i) {
      return {
        id: 1001 + i, row_index: i, source: r[0], verbatim_analyse: r[1], nb_themes: 1,
        theme1_niv1: r[2], theme1_niv2: r[3], theme1_sentiment: r[4], theme1_score: Math.min(0.99, r[6] + 0.05),
        theme2_niv1: null, theme2_niv2: null, theme2_sentiment: null, theme2_score: Math.max(0.20, r[6] - 0.07),
        signal_rupture: r[5].indexOf('RUP') >= 0, signal_churn: r[5].indexOf('CHU') >= 0, signal_insatisfaction: r[5].indexOf('INS') >= 0,
        confidence_globale: r[6], revue_requise: r[7] === 'revue', corrected: r[7] === 'corrige', reviewed: r[7] === 'corrige'
      };
    });
    var batches = [
      { id: 2487, label: 'Avis MDTC + Mopinion · Mai 2026', status: 'done', created_at: '2026-05-31T18:02:00Z', model_label: 'CamemBERT', seuil_revue: 0.5, n_total: 11240, n_processed: 11240, n_review: 944, n_errors: 0, duration_s: 460 },
      { id: 2488, label: 'Relances post-SAV · S22', status: 'running', created_at: '2026-06-03T09:10:00Z', model_label: 'CamemBERT', seuil_revue: 0.5, n_total: 4200, n_processed: 2604, n_review: 294, n_errors: 0, duration_s: null },
      { id: 2489, label: 'Test moteur LM Studio', status: 'pending', created_at: '2026-06-04T08:00:00Z', model_label: 'LM Studio', seuil_revue: 0.5, n_total: 1500, n_processed: 0, n_review: 0, n_errors: 0, duration_s: null },
      { id: 2486, label: 'Avis avril 2026', status: 'done', created_at: '2026-04-30T17:00:00Z', model_label: 'CamemBERT', seuil_revue: 0.5, n_total: 10870, n_processed: 10870, n_review: 989, n_errors: 0, duration_s: 455 },
      { id: 2485, label: 'Lot incomplet (fichier corrompu)', status: 'failed', created_at: '2026-04-12T10:00:00Z', model_label: 'Démo', seuil_revue: 0.5, n_total: 0, n_processed: 510, n_review: 0, n_errors: 510, duration_s: null, error_message: 'Fichier illisible' },
      { id: 2480, label: 'Import mars 2026', status: 'done', created_at: '2026-03-31T16:00:00Z', model_label: 'CamemBERT', seuil_revue: 0.5, n_total: 11010, n_processed: 11010, n_review: 969, n_errors: 0, duration_s: 470 },
      { id: 2483, label: 'Essai démo (annulé)', status: 'canceled', created_at: '2026-04-02T09:00:00Z', model_label: 'Démo', seuil_revue: 0.5, n_total: 0, n_processed: 270, n_review: 0, n_errors: 0, duration_s: null }
    ];
    var users = [
      { id: 1, username: 'c.lambert', role: 'admin', is_active: true, created_at: '2026-01-10T09:00:00Z' },
      { id: 2, username: 'a.moreau', role: 'admin', is_active: true, created_at: '2026-01-10T09:00:00Z' },
      { id: 3, username: 's.benali', role: 'analyste', is_active: true, created_at: '2026-02-01T09:00:00Z' },
      { id: 4, username: 'j.petit', role: 'analyste', is_active: true, created_at: '2026-05-15T09:00:00Z' },
      { id: 5, username: 'm.dubois', role: 'analyste', is_active: false, created_at: '2026-01-20T09:00:00Z' },
      { id: 6, username: 'admin', role: 'admin', is_active: true, created_at: '2026-01-01T09:00:00Z' }
    ];
    var audit = [
      { id: 9, user: 'a.moreau', action: 'model.activate', entity: 'model', entity_id: 'CamemBERT', details: 'Défini comme moteur actif', created_at: '2026-06-03T14:22:00Z' },
      { id: 8, user: 'c.lambert', action: 'batch.create', entity: 'batch', entity_id: '2488', details: 'Seuil de revue 0,50', created_at: '2026-06-03T09:10:00Z' },
      { id: 7, user: 'a.moreau', action: 'user.create', entity: 'user', entity_id: 'j.petit', details: 'Rôle Analyste', created_at: '2026-06-02T17:48:00Z' },
      { id: 6, user: 'c.lambert', action: 'results.export', entity: 'batch', entity_id: '2487', details: 'XLSX · 11 240 lignes', created_at: '2026-05-31T18:02:00Z' },
      { id: 5, user: 's.benali', action: 'result.correct', entity: 'batch', entity_id: '2487', details: '312 verbatims corrigés', created_at: '2026-05-31T16:30:00Z' },
      { id: 4, user: 'a.moreau', action: 'data.purge', entity: 'retention', entity_id: '', details: 'Lots > 12 mois supprimés', created_at: '2026-05-28T11:15:00Z' },
      { id: 3, user: 'a.moreau', action: 'user.deactivate', entity: 'user', entity_id: 'm.dubois', details: 'Départ collaborateur', created_at: '2026-05-27T10:00:00Z' },
      { id: 2, user: 'c.lambert', action: 'auth.login', entity: '', entity_id: '', details: 'Session ouverte', created_at: '2026-05-24T08:40:00Z' },
      { id: 1, user: 'a.moreau', action: 'config.update', entity: 'config', entity_id: '', details: '0,55 → 0,50', created_at: '2026-05-20T15:20:00Z' }
    ];
    var models = [
      { id: 1, kind: 'real', label: 'CamemBERT', is_active: true, available: true, metrics: { f1_macro_niv1: 0.86, f1_macro_niv2: 0.74, accuracy_sentiment: 0.91, recall_rupture: 0.68 }, registered_at: '2026-05-01T09:00:00Z' },
      { id: 2, kind: 'lmstudio', label: 'LM Studio', is_active: false, available: true, metrics: { f1_macro_niv1: 0.82 }, registered_at: '2026-05-10T09:00:00Z' },
      { id: 3, kind: 'stub', label: 'Démo', is_active: false, available: true, metrics: { f1_macro_niv1: 0.61 }, registered_at: '2026-01-01T09:00:00Z' }
    ];
    return { THEMES: THEMES, results: results, batches: batches, users: users, audit: audit, models: models, config: { retention_months: '12', default_seuil_revue: '0.50' } };
  })();

  // état mutable de la démo (revue, lot en cours)
  var demoState = { reviewed: {}, corrected: {}, nextBatchId: 2490, running: {} };
  function delay(v, ms) { return new Promise(function (r) { setTimeout(function () { r(v); }, ms || 120); }); }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function demoResult(r) {
    var x = clone(r);
    if (demoState.reviewed[r.id]) { x.reviewed = true; x.revue_requise = false; }
    if (demoState.corrected[r.id]) { x.corrected = true; }
    return x;
  }

  var demo = {
    health: function () { return delay({ status: 'ok', app: 'Observatoire Ecom Studio', version: 'demo', env: 'demo' }); },
    login: function (username, password) {
      if (username && username.trim() && password && password.trim()) return delay({ id: 1, username: username.trim(), role: 'admin' }, 250);
      return delay().then(function () { var e = new ApiError(401, 'Identifiants invalides'); throw e; });
    },
    logout: function () { return delay({ status: 'ok' }); },
    me: function () { return delay({ id: 1, username: 'c.lambert', role: 'admin' }); },
    changePassword: function (cur, neu) {
      if (!cur) return delay().then(function () { throw new ApiError(400, 'Mot de passe actuel incorrect'); });
      return delay({ status: 'ok' }, 250);
    },
    listUsers: function () { return delay(clone(D.users)); },
    createUser: function (u, p, role) { return delay({ id: 99, username: u, role: role, is_active: true, created_at: new Date(0).toISOString() }); },
    updateUser: function (id, patch) { var u = D.users.filter(function (x) { return x.id === id; })[0]; return delay(Object.assign(clone(u || {}), patch)); },
    deactivateUser: function (id) { var u = D.users.filter(function (x) { return x.id === id; })[0]; return delay(Object.assign(clone(u || {}), { is_active: false })); },

    listBatches: function () {
      var extra = Object.keys(demoState.running).map(function (k) { return demoState.running[k].batch; });
      return delay(extra.concat(clone(D.batches)));
    },
    getBatch: function (id) {
      id = Number(id);
      if (demoState.running[id]) return delay(_progressBatch(id));
      var b = D.batches.filter(function (x) { return x.id === id; })[0] || D.batches[0];
      return delay(clone(b));
    },
    getBatchProgress: function (id) {
      id = Number(id);
      var b = demoState.running[id] ? _progressBatch(id) : (D.batches.filter(function (x) { return x.id === id; })[0] || D.batches[0]);
      return delay({ id: b.id, status: b.status, n_total: b.n_total, n_processed: b.n_processed, progress: b.n_total ? b.n_processed / b.n_total : 0 }, 90);
    },
    cancelBatch: function (id) { id = Number(id); if (demoState.running[id]) { demoState.running[id].batch.status = 'canceled'; } return delay(clone((demoState.running[id] || {}).batch || {})); },
    createBatch: function (opts) {
      var id = demoState.nextBatchId++;
      var b = { id: id, label: opts.label || ('lot-' + id), status: 'running', created_at: new Date(0).toISOString(), model_label: 'CamemBERT', seuil_revue: opts.seuilRevue, n_total: 11240, n_processed: 0, n_review: 0, n_errors: 0, duration_s: null };
      demoState.running[id] = { batch: b, start: Date.now ? null : null };
      demoState.running[id].t0 = performance.now();
      return delay(clone(b), 300);
    },

    listResults: function (batchId, f) {
      f = f || {};
      var items = D.results.map(demoResult).filter(function (r) {
        if (f.q && r.verbatim_analyse.toLowerCase().indexOf(String(f.q).toLowerCase()) < 0) return false;
        if (f.niv1 && (String(r.theme1_niv1) + ' ' + String(r.theme1_niv2)).toLowerCase().indexOf(String(f.niv1).toLowerCase()) < 0) return false;
        if (f.sentiment && r.theme1_sentiment !== f.sentiment) return false;
        if (f.rupture && !r.signal_rupture) return false;
        if (f.churn && !r.signal_churn) return false;
        if (f.insatisfaction && !r.signal_insatisfaction) return false;
        if (f.revue === true && !r.revue_requise) return false;
        if (f.revue === false && r.revue_requise) return false;
        return true;
      });
      var off = f.offset || 0, lim = f.limit == null ? 50 : f.limit;
      return delay({ total: items.length, limit: lim, offset: off, items: items.slice(off, off + lim) });
    },
    exportUrl: function () { return '#demo-export'; },
    exportCorrectionsUrl: function () { return '#demo-export'; },
    getReviewQueue: function (batchId, offset, limit) {
      var items = D.results.map(demoResult).filter(function (r) { return r.revue_requise && !r.reviewed; })
        .sort(function (a, b) { return a.confidence_globale - b.confidence_globale; });
      return delay({ total: items.length, limit: limit == null ? 50 : limit, offset: offset || 0, items: items });
    },
    correctResult: function (id, payload) {
      demoState.reviewed[id] = true;
      if (payload && payload.action === 'correct') demoState.corrected[id] = true;
      var r = D.results.filter(function (x) { return x.id === id; })[0];
      return delay(demoResult(r || D.results[0]), 150);
    },
    getTaxonomy: function () {
      var themes = Object.keys(D.THEMES).map(function (k) { return { niv1: k, niv2: D.THEMES[k] }; });
      return delay({ themes: themes });
    },

    getBatchKpi: function (id) {
      return delay({
        batch_id: Number(id), label: (D.batches.filter(function (x) { return x.id === Number(id); })[0] || {}).label || '', status: 'done',
        model_label: 'CamemBERT', n_total: 11240, n_processed: 11240, n_review: 944, review_rate: 0.084, n_errors: 0, duration_s: 460,
        themes: { 'Livraison': 3102, 'Produit': 2245, 'Site web': 1638, 'Relation client': 1312, 'Paiement': 831, 'Magasin': 712 },
        subthemes: {}, sentiments: { 'Négatif': 6070, 'Neutre': 2473, 'Positif': 2697 }, sources: { MDTC: 6100, Mopinion: 5140 },
        signals: { rupture: 426, churn: 273, insatisfaction: 341 },
        theme_sentiment: {
          'Livraison': { 'Négatif': 2480, 'Neutre': 410, 'Positif': 212 }, 'Produit': { 'Négatif': 1520, 'Neutre': 360, 'Positif': 365 },
          'Site web': { 'Négatif': 1180, 'Neutre': 300, 'Positif': 158 }, 'Relation client': { 'Négatif': 612, 'Neutre': 240, 'Positif': 460 },
          'Paiement': { 'Négatif': 690, 'Neutre': 96, 'Positif': 45 }
        }
      });
    },
    getVolumetry: function () {
      var done = D.batches.filter(function (b) { return b.status === 'done'; });
      var series = [
        { id: 1, label: 'Jan', created_at: '2026-01-31', n_total: 9800, n_review: 800, review_rate: 0.082, signals: { rupture: 300, churn: 200, insatisfaction: 250 } },
        { id: 2, label: 'Fév', created_at: '2026-02-28', n_total: 10200, n_review: 840, review_rate: 0.082, signals: { rupture: 310, churn: 210, insatisfaction: 260 } },
        { id: 3, label: 'Mar', created_at: '2026-03-31', n_total: 11010, n_review: 969, review_rate: 0.088, signals: { rupture: 410, churn: 260, insatisfaction: 320 } },
        { id: 4, label: 'Avr', created_at: '2026-04-30', n_total: 10870, n_review: 989, review_rate: 0.091, signals: { rupture: 400, churn: 250, insatisfaction: 310 } },
        { id: 5, label: 'Mai', created_at: '2026-05-31', n_total: 11240, n_review: 944, review_rate: 0.084, signals: { rupture: 426, churn: 273, insatisfaction: 341 } }
      ];
      return delay({
        n_batches: done.length, total_verbatims: 53120,
        series: series,
        global_themes: { 'Livraison': 3102, 'Produit': 2245, 'Site web': 1638, 'Relation client': 1312, 'Paiement': 831 },
        theme_sentiment: {
          'Livraison': { 'Négatif': 2480, 'Neutre': 410, 'Positif': 212 }, 'Produit': { 'Négatif': 1520, 'Neutre': 360, 'Positif': 365 },
          'Site web': { 'Négatif': 1180, 'Neutre': 300, 'Positif': 158 }, 'Relation client': { 'Négatif': 612, 'Neutre': 240, 'Positif': 460 },
          'Paiement': { 'Négatif': 690, 'Neutre': 96, 'Positif': 45 }
        }
      });
    },
    getModelKpi: function () { return delay({ active: { label: 'CamemBERT', kind: 'real', available: true, metrics: { f1_macro_niv1: 0.86, f1_macro_niv2: 0.74, accuracy_sentiment: 0.91, recall_rupture: 0.68 } } }); },

    listModels: function () { return delay(clone(D.models)); },
    activateModel: function (id) { return delay(clone(D.models.filter(function (m) { return m.id === id; })[0] || D.models[0])); },
    rescanModels: function () { return delay({ status: 'ok' }); },

    getAudit: function (limit) { return delay(clone(D.audit).slice(0, limit || 100)); },
    getConfig: function () { return delay(clone(D.config)); },
    patchConfig: function (p) { if (p.retention_months != null) D.config.retention_months = String(p.retention_months); if (p.default_seuil_revue != null) D.config.default_seuil_revue = String(p.default_seuil_revue); return delay(clone(D.config)); },
    purge: function () { return delay({ batches: 0, cutoff: null }); },
    getOps: function () {
      return delay({
        batches: { total: 142, by_status: { done: 132, failed: 4, canceled: 6 }, failure_rate: 0.028, avg_duration_s: 460 },
        retention_months: Number(D.config.retention_months), purge_cutoff: null, purgeable_batches: 0,
        disk: { uploads_bytes: 12 * 1e9, output_bytes: 6.4 * 1e9, free_bytes: 31.6 * 1e9, total_bytes: 50 * 1e9 }
      });
    },
    getMeta: function () { return delay({ default_seuil_revue: 0.5, active_model: { label: 'CamemBERT', kind: 'real' } }); },
    predict: function (text, satisfaction) {
      return delay(null, 700).then(function () {
        var low = (text || '').toLowerCase();
        var neg = /(jamais|défect|rembours|annul|injoign|rupture|pas|lent|floué|incompréh)/.test(low);
        var pos = /(merci|parfait|super|excellent|rapide|aimable|satisfait|bonne)/.test(low);
        var sent = pos && !neg ? 'Positif' : (neg ? 'Négatif' : 'Neutre');
        var t1 = /livr|colis|transport/.test(low) ? 'Livraison' : (/rembours|pai|factur/.test(low) ? 'Paiement' : (/site|connect|bug|compte/.test(low) ? 'Site web' : 'Produit'));
        var t2 = (D.THEMES[t1] || ['Qualité'])[0];
        return {
          verbatim_analysé: text, nb_themes: 1, theme1_niv1: t1, theme1_niv2: t2, theme1_sentiment: sent, theme1_score_confiance: 0.8,
          theme2_niv1: '', theme2_niv2: '', theme2_sentiment: '',
          signal_rupture_client: /rupture|jamais reçu|injoign/.test(low), signal_churn: /plus jamais|annul|résili/.test(low),
          signal_insatisfaction_forte: neg && /défect|floué|inadmiss|honteux/.test(low),
          confidence_globale: sent === 'Neutre' ? 0.58 : 0.86, revue_humaine_requise: false, model_label: 'CamemBERT (démo)'
        };
      });
    }
  };
  function _progressBatch(id) {
    var st = demoState.running[id];
    if (!st) return D.batches[0];
    var b = st.batch;
    if (b.status === 'canceled') return b;
    var elapsed = (performance.now() - st.t0);
    var p = Math.min(1, elapsed / 4200);
    b.n_processed = Math.round(p * b.n_total);
    if (p >= 1) { b.status = 'done'; b.n_processed = b.n_total; b.n_review = Math.round(b.n_total * 0.078); b.duration_s = 4; }
    return b;
  }

  window.API = Object.assign({ isDemo: function () { return DEMO; } }, DEMO ? demo : live);
  window.API.ApiError = ApiError;
})();
