// Client API. Étoffé au fil des lots.

export type Role = "analyste" | "admin";

export interface Health {
  status: string;
  app: string;
  version: string;
  env?: string;
  components?: Record<string, boolean>;
}

export interface Me {
  id: number;
  username: string;
  role: Role;
}

export interface User {
  id: number;
  username: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const getHealth = () => request<Health>("/api/health");

// --- Auth ---
export const login = (username: string, password: string) =>
  request<Me>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
export const logout = () => request<{ status: string }>("/api/auth/logout", { method: "POST" });
export const getMe = () => request<Me>("/api/auth/me");

// --- Users (admin) ---
export const listUsers = () => request<User[]>("/api/users");
export const createUser = (username: string, password: string, role: Role) =>
  request<User>("/api/users", { method: "POST", body: JSON.stringify({ username, password, role }) });
export const updateUser = (id: number, patch: Partial<{ role: Role; is_active: boolean; password: string }>) =>
  request<User>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
export const deactivateUser = (id: number) => request<User>(`/api/users/${id}`, { method: "DELETE" });

// --- Lots (batches) ---
export interface Batch {
  id: number;
  label: string;
  status: string; // pending | running | done | failed | canceled
  created_by?: number | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  model_label?: string | null;
  seuil_revue: number;
  refiner_label?: string | null;          // cascade V5 (null = mono-moteur)
  chain_disagreements?: number | null;    // nb de désaccords proposeur/raffineur
  n_total: number;
  n_processed: number;
  n_review: number;
  n_errors: number;
  duration_s?: number | null;
  error_message?: string | null;
}

export interface BatchProgress {
  id: number;
  status: string;
  n_total: number;
  n_processed: number;
  progress: number;
}

export const listBatches = () => request<Batch[]>("/api/batches");
export const getBatch = (id: number) => request<Batch>(`/api/batches/${id}`);
export const getBatchProgress = (id: number) => request<BatchProgress>(`/api/batches/${id}/progress`);
export const cancelBatch = (id: number) => request<Batch>(`/api/batches/${id}/cancel`, { method: "POST" });

export async function createBatch(opts: {
  label?: string;
  seuilRevue: number;
  refinerLabel?: string | null;   // cascade V5 (LLM local) — optionnel
  mdtc?: File | null;
  mopinion?: File | null;
}): Promise<Batch> {
  const form = new FormData();
  if (opts.label) form.append("label", opts.label);
  form.append("seuil_revue", String(opts.seuilRevue));
  if (opts.refinerLabel) form.append("refiner_label", opts.refinerLabel);
  if (opts.mdtc) form.append("mdtc", opts.mdtc);
  if (opts.mopinion) form.append("mopinion", opts.mopinion);
  // Pas de Content-Type manuel : le navigateur pose le boundary multipart.
  const res = await fetch("/api/batches", { method: "POST", credentials: "include", body: form });
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try {
      const b = await res.json();
      if (b?.detail) detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

// --- Modèles ---
export interface ModelVersion {
  id: number;
  kind: string; // stub | real
  label: string;
  is_active: boolean;
  available: boolean;
  metrics?: Record<string, unknown> | null;
  registered_at?: string | null;
}
export const listModels = () => request<ModelVersion[]>("/api/models");
export const activateModel = (id: number) => request<ModelVersion>(`/api/models/${id}/activate`, { method: "POST" });
export const rescanModels = () => request<{ status: string }>("/api/models/rescan", { method: "POST" });

// --- Comparaison de moteurs (V5) ---
export interface ComparisonMetrics {
  engines: string[];
  sample_size: number;
  agreement: Record<string, number>;            // "A vs B" -> part d'accord [0,1]
  confidence: Record<string, { moyenne: number; min: number; max: number; n: number }>;
  latency_ms: Record<string, number>;
  sentiment: Record<string, Record<string, number>>;
  n_divergences: number;
  judge: JudgeMetrics | null;                    // null = juge non exécuté (mode dégradé)
}
export interface JudgeMetrics {
  win_rate: Record<string, number>;              // moteur -> % de victoires (sur ses duels jugés)
  wins: Record<string, number>;
  n_judged: number;                              // nb de duels jugés (sur divergences)
  n_ties: number;
}
export interface JudgeVerdict {
  id: number;
  result_id: number | null;
  row_index?: number | null;
  verbatim?: string | null;
  engine_a: string;
  engine_b: string;
  classif_a?: string | null;
  classif_b?: string | null;
  winner: "a" | "b" | "tie";
  rationale: string | null;
}
export interface VerdictsPage { total: number; offset: number; limit: number; items: JudgeVerdict[] }
export const getVerdicts = (id: number, offset = 0, limit = 20) =>
  request<VerdictsPage>(`/api/comparisons/${id}/verdicts?offset=${offset}&limit=${limit}`);
export interface ComparisonRun {
  id: number;
  batch_id: number;
  status: string;                                // pending | running | done | failed | canceled
  created_at?: string | null;
  engine_labels: string[];
  sample_size: number;
  seed: number;
  judge_enabled: boolean;
  metrics?: ComparisonMetrics | null;
  error_message?: string | null;
}
export const listComparisons = (batchId: number) =>
  request<ComparisonRun[]>(`/api/comparisons?batch_id=${batchId}`);
export const getComparison = (id: number) => request<ComparisonRun>(`/api/comparisons/${id}`);
export const createComparison = (
  batchId: number,
  body: { engines: string[]; sample_size: number; seed: number; judge_enabled: boolean },
) => request<ComparisonRun>(`/api/batches/${batchId}/comparisons`, { method: "POST", body: JSON.stringify(body) });
export const comparisonExportUrl = (id: number) => `/api/comparisons/${id}/export`;

// --- Résultats ---
export interface ResultRow {
  id: number;
  row_index: number;
  source?: string | null;
  verbatim_analyse: string;
  nb_themes: number;
  theme1_niv1?: string | null;
  theme1_niv2?: string | null;
  theme1_sentiment?: string | null;
  theme1_score?: number | null;
  theme2_niv1?: string | null;
  theme2_niv2?: string | null;
  theme2_sentiment?: string | null;
  signal_rupture: boolean;
  signal_churn: boolean;
  signal_insatisfaction: boolean;
  confidence_globale?: number | null;
  revue_requise: boolean;
  corrected: boolean;
}
export interface ResultsResponse {
  total: number;
  limit: number;
  offset: number;
  items: ResultRow[];
}
export interface ResultFilters {
  niv1?: string;
  sentiment?: string;
  revue?: boolean;
  rupture?: boolean;
  churn?: boolean;
  insatisfaction?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}
// Sérialise les filtres (sans pagination) — partagé par la liste et l'export,
// pour que l'export honore exactement les filtres affichés à l'écran.
function resultFilterParams(f: ResultFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.niv1) p.set("niv1", f.niv1);
  if (f.sentiment) p.set("sentiment", f.sentiment);
  if (f.revue !== undefined) p.set("revue", String(f.revue));
  if (f.rupture) p.set("rupture", "true");
  if (f.churn) p.set("churn", "true");
  if (f.insatisfaction) p.set("insatisfaction", "true");
  if (f.q) p.set("q", f.q);
  return p;
}
export function listResults(batchId: number, f: ResultFilters = {}): Promise<ResultsResponse> {
  const p = resultFilterParams(f);
  p.set("limit", String(f.limit ?? 50));
  p.set("offset", String(f.offset ?? 0));
  return request<ResultsResponse>(`/api/batches/${batchId}/results?${p.toString()}`);
}
export const exportUrl = (batchId: number, format: "csv" | "xlsx", filters: ResultFilters = {}) => {
  const p = resultFilterParams(filters);
  p.set("format", format);
  return `/api/batches/${batchId}/export?${p.toString()}`;
};

// --- Test à la volée ---
export interface Prediction {
  "verbatim_analysé": string;
  nb_themes: number;
  theme1_niv1: string;
  theme1_niv2: string;
  theme1_sentiment: string;
  theme1_score_confiance: number | string;
  theme2_niv1: string;
  theme2_niv2: string;
  theme2_sentiment: string;
  signal_rupture_client: boolean;
  signal_churn: boolean;
  signal_insatisfaction_forte: boolean;
  confidence_globale: number | string;
  revue_humaine_requise: boolean;
  model_label?: string | null;
}
export const predict = (text: string, satisfaction?: number | null, modelId?: number | null) =>
  request<Prediction>("/api/predict", {
    method: "POST",
    body: JSON.stringify({ text, satisfaction: satisfaction ?? null, model_id: modelId ?? null }),
  });

// --- Revue humaine ---
export interface TaxonomyTheme { niv1: string; niv2: string[] }
export const getTaxonomy = () => request<{ themes: TaxonomyTheme[] }>("/api/taxonomy");
export const getReviewQueue = (batchId: number, offset = 0, limit = 1) =>
  request<ResultsResponse>(`/api/batches/${batchId}/review?limit=${limit}&offset=${offset}`);

export interface CorrectionPayload {
  action: "validate" | "correct";
  theme1_niv1?: string;
  theme1_niv2?: string;
  theme1_sentiment?: string;
  signal_rupture?: boolean;
  signal_churn?: boolean;
  signal_insatisfaction?: boolean;
}
export const correctResult = (id: number, p: CorrectionPayload) =>
  request<ResultRow>(`/api/results/${id}`, { method: "PATCH", body: JSON.stringify(p) });
export const exportCorrectionsUrl = () => "/api/corrections/export";

// --- KPI / tableaux de bord ---
export interface BatchKpi {
  batch_id: number;
  label: string;
  model_label?: string | null;
  n_total: number;
  n_review: number;
  review_rate: number;
  n_errors: number;
  duration_s?: number | null;
  themes: Record<string, number>;
  subthemes: Record<string, number>;
  sentiments: Record<string, number>;
  sources: Record<string, number>;
  signals: { rupture: number; churn: number; insatisfaction: number };
  theme_sentiment: Record<string, Record<string, number>>;
}
export interface VolumetrySeriesItem {
  id: number; label: string; created_at?: string | null;
  n_total: number; n_review: number; review_rate: number;
  signals: { rupture: number; churn: number; insatisfaction: number };
}
export interface Volumetry {
  n_batches: number;
  total_verbatims: number;
  series: VolumetrySeriesItem[];
  global_themes: Record<string, number>;
  theme_sentiment: Record<string, Record<string, number>>;
}
export interface ModelKpi {
  active: null | { label: string; kind: string; available: boolean; metrics?: Record<string, number> | null };
}
export const getBatchKpi = (id: number) => request<BatchKpi>(`/api/batches/${id}/kpi`);
export const getVolumetry = () => request<Volumetry>("/api/kpi/volumetry");
export const getModelKpi = () => request<ModelKpi>("/api/kpi/model");

// --- Admin (audit, config, purge) ---
export interface AuditEntry {
  id: number; user?: string | null; action: string;
  entity?: string | null; entity_id?: string | null; details?: string | null;
  created_at?: string | null;
}
export interface AppConfigValues { retention_months: string; default_seuil_revue: string }
export const getAudit = (limit = 100) => request<AuditEntry[]>(`/api/audit?limit=${limit}`);
export const getConfig = () => request<AppConfigValues>("/api/config");
export const patchConfig = (p: Partial<{ retention_months: number; default_seuil_revue: number }>) =>
  request<AppConfigValues>("/api/config", { method: "PATCH", body: JSON.stringify(p) });
export const purgeData = () => request<{ batches: number; cutoff: string | null }>("/api/admin/purge", { method: "POST" });

export interface OpsKpi {
  batches: { total: number; by_status: Record<string, number>; failure_rate: number; avg_duration_s: number | null };
  retention_months: number;
  purge_cutoff: string | null;
  purgeable_batches: number;
  disk: { uploads_bytes: number; output_bytes: number; free_bytes: number; total_bytes: number };
}
export const getOps = () => request<OpsKpi>("/api/admin/ops");

// --- Métadonnées (page d'aide, info-bulles) ---
export interface AppMeta {
  default_seuil_revue: number;
  active_model: { label: string; kind: string } | null;
}
export const getMeta = () => request<AppMeta>("/api/meta");

// --- Compte (mot de passe) ---
export const changePassword = (current_password: string, new_password: string) =>
  request<{ status: string }>("/api/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) });

export { ApiError };
