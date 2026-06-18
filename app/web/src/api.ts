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

export async function createBatch(opts: {
  label?: string;
  seuilRevue: number;
  mdtc?: File | null;
  mopinion?: File | null;
}): Promise<Batch> {
  const form = new FormData();
  if (opts.label) form.append("label", opts.label);
  form.append("seuil_revue", String(opts.seuilRevue));
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
export function listResults(batchId: number, f: ResultFilters = {}): Promise<ResultsResponse> {
  const p = new URLSearchParams();
  if (f.niv1) p.set("niv1", f.niv1);
  if (f.sentiment) p.set("sentiment", f.sentiment);
  if (f.revue !== undefined) p.set("revue", String(f.revue));
  if (f.rupture) p.set("rupture", "true");
  if (f.churn) p.set("churn", "true");
  if (f.insatisfaction) p.set("insatisfaction", "true");
  if (f.q) p.set("q", f.q);
  p.set("limit", String(f.limit ?? 50));
  p.set("offset", String(f.offset ?? 0));
  return request<ResultsResponse>(`/api/batches/${batchId}/results?${p.toString()}`);
}
export const exportUrl = (batchId: number, format: "csv" | "xlsx") =>
  `/api/batches/${batchId}/export?format=${format}`;

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
export const predict = (text: string, satisfaction?: number | null) =>
  request<Prediction>("/api/predict", { method: "POST", body: JSON.stringify({ text, satisfaction: satisfaction ?? null }) });

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

export { ApiError };
