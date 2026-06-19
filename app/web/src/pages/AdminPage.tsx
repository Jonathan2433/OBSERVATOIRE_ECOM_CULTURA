import { useEffect, useState, type FormEvent } from "react";
import {
  activateModel, getAudit, getConfig, getOps, listModels, patchConfig, purgeData, rescanModels,
  type AppConfigValues, type AuditEntry, type ModelVersion, type OpsKpi,
} from "../api";
import { Badge, Button, Card, Dialog, EmptyState, Input, StatCard } from "../ui";

type Tab = "config" | "modeles" | "ops" | "retention" | "audit";

function fmtBytes(n: number): string {
  if (!n) return "0 o";
  const u = ["o", "Ko", "Mo", "Go", "To"];
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
}

const KIND_LABEL: Record<string, string> = { real: "CamemBERT", lmstudio: "LM Studio (LLM)", stub: "Démo" };
const kindTone = (k: string) => (k === "real" ? "success" : k === "lmstudio" ? "info" : "neutral");

/** Motif d'indisponibilité d'un moteur LM Studio (sinon null). */
function lmStudioReason(m: ModelVersion): string | null {
  if (m.kind !== "lmstudio" || m.available) return null;
  const r = (m.metrics ?? {}) as { reachable?: boolean; model_present?: boolean };
  if (!r.reachable) return "LM Studio injoignable";
  if (!r.model_present) return "modèle non chargé dans LM Studio";
  return "indisponible";
}

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("config");
  const [cfg, setCfg] = useState<AppConfigValues | null>(null);
  const [ops, setOps] = useState<OpsKpi | null>(null);
  const [models, setModels] = useState<ModelVersion[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [retention, setRetention] = useState("13");
  const [seuil, setSeuil] = useState("0.50");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [purging, setPurging] = useState(false);

  const refresh = () => {
    getConfig().then((c) => { setCfg(c); setRetention(c.retention_months); setSeuil(c.default_seuil_revue); })
      .catch((e) => setError(String(e.message ?? e)));
    getAudit(100).then(setAudit).catch(() => setAudit([]));
    getOps().then(setOps).catch(() => setOps(null));
    listModels().then(setModels).catch(() => setModels([]));
  };

  const activate = async (id: number) => {
    setMsg(null); setError(null);
    try { await activateModel(id); setMsg("Modèle activé."); refresh(); }
    catch (err: any) { setError(err?.message ?? "Erreur"); }
  };
  const rescan = async () => {
    setMsg(null); setError(null);
    try { await rescanModels(); setMsg("Re-scan demandé : le worker détecte les modèles déposés. Rafraîchissez dans quelques secondes."); }
    catch (err: any) { setError(err?.message ?? "Erreur"); }
  };
  useEffect(() => { refresh(); }, []);

  const saveConfig = async (e: FormEvent) => {
    e.preventDefault();
    setMsg(null); setError(null);
    try {
      await patchConfig({ retention_months: parseInt(retention, 10), default_seuil_revue: parseFloat(seuil) });
      setMsg("Configuration enregistrée.");
      refresh();
    } catch (err: any) { setError(err?.message ?? "Erreur"); }
  };

  const doPurge = async () => {
    setMsg(null); setError(null); setPurging(true);
    try {
      const r = await purgeData();
      setMsg(`Purge effectuée : ${r.batches} lot(s) supprimé(s).`);
      refresh();
    } catch (err: any) { setError(err?.message ?? "Erreur"); }
    finally { setPurging(false); setConfirmPurge(false); }
  };

  const tabBtn = (key: Tab, label: string) => (
    <button className={"ui-tab" + (tab === key ? " is-active" : "")} onClick={() => setTab(key)}>{label}</button>
  );

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Administration</h1>
        <p className="page-header__sub">Configuration applicative, rétention RGPD et journal d'audit.</p>
      </div>

      {msg && <p style={{ color: "var(--cu-success)" }}>{msg}</p>}
      {error && <p className="ui-field__error">{error}</p>}

      <nav className="ui-tabs" aria-label="Sections d'administration">
        {tabBtn("config", "Configuration")}
        {tabBtn("modeles", "Modèles")}
        {tabBtn("ops", "Exploitation")}
        {tabBtn("retention", "Rétention")}
        {tabBtn("audit", "Journal d'audit")}
      </nav>

      {tab === "config" && (
        <Card title="Configuration">
          {!cfg ? <p className="ui-muted">Chargement…</p> : (
            <form onSubmit={saveConfig} className="ui-stack" style={{ maxWidth: 360 }}>
              <Input label="Rétention des données (mois)" type="number" min={0}
                     value={retention} onChange={(e) => setRetention(e.target.value)} />
              <Input label="Seuil de revue par défaut" type="number" min={0} max={1} step={0.05}
                     value={seuil} onChange={(e) => setSeuil(e.target.value)}
                     hint="S'applique aux nouveaux lots ; les lots passés conservent leur seuil." />
              <div><Button type="submit" variant="primary">Enregistrer</Button></div>
            </form>
          )}
        </Card>
      )}

      {tab === "modeles" && (
        <Card title="Modèles" actions={<Button variant="secondary" size="sm" onClick={rescan}>Re-scanner</Button>}>
          <p className="ui-muted" style={{ marginBottom: "var(--sp-3)" }}>
            Après avoir déposé un modèle entraîné dans <code>data/models</code> et redémarré le worker,
            re-scannez puis activez la version souhaitée. Le moteur <b>LM Studio (LLM)</b> n'apparaît que
            s'il est activé en configuration ; pour lui, <b>Re-scanner</b> teste la connexion à LM Studio.
          </p>
          {models.length === 0 ? (
            <EmptyState title="Aucun modèle détecté" description="Déposez un modèle puis re-scannez." />
          ) : (
            <div className="ui-table-wrap">
              <table className="ui-table">
                <thead>
                  <tr><th>Version</th><th>Type</th><th>Disponible</th><th>État</th><th>KPI</th><th></th></tr>
                </thead>
                <tbody>
                  {models.map((m) => (
                    <tr key={m.id}>
                      <td>{m.label}</td>
                      <td><Badge tone={kindTone(m.kind)}>{KIND_LABEL[m.kind] ?? m.kind}</Badge></td>
                      <td>
                        {m.available ? <Badge tone="success" dot>oui</Badge> : <Badge tone="danger">non</Badge>}
                        {lmStudioReason(m) && <span className="ui-muted" style={{ marginLeft: 6 }}>{lmStudioReason(m)}</span>}
                      </td>
                      <td>{m.is_active ? <Badge tone="primary" dot>actif</Badge> : <span className="ui-muted">—</span>}</td>
                      <td>{m.metrics && Object.keys(m.metrics).length > 0 ? <Badge tone="info">disponibles</Badge> : <span className="ui-muted">—</span>}</td>
                      <td style={{ textAlign: "right" }}>
                        {!m.is_active && m.available && (
                          <Button variant="primary" size="sm" onClick={() => activate(m.id)}>Activer</Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "ops" && (
        <div className="ui-stack">
          {!ops ? <p className="ui-muted">Chargement…</p> : (
            <>
              <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
                <StatCard label="Lots traités" value={ops.batches.total} />
                <StatCard label="Taux d'échec des jobs" value={`${(ops.batches.failure_rate * 100).toFixed(1)} %`} />
                <StatCard label="Durée moyenne" value={ops.batches.avg_duration_s != null ? `${ops.batches.avg_duration_s.toFixed(0)} s` : "—"} />
                <StatCard label="Lots purgeables" value={ops.purgeable_batches}
                          hint={ops.purge_cutoff ? `avant ${ops.purge_cutoff.slice(0, 10)}` : `rétention ${ops.retention_months} mois`} />
              </div>
              <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
                <StatCard label="Espace disque libre" value={fmtBytes(ops.disk.free_bytes)}
                          hint={`sur ${fmtBytes(ops.disk.total_bytes)}`} />
                <StatCard label="Fichiers déposés" value={fmtBytes(ops.disk.uploads_bytes)} hint="uploads" />
                <StatCard label="Exports" value={fmtBytes(ops.disk.output_bytes)} hint="output" />
              </div>
              <Card title="Lots par statut">
                <div className="ui-row ui-row--wrap">
                  {Object.entries(ops.batches.by_status).map(([s, n]) => (
                    <span key={s} className="ui-chip">{s} : {n}</span>
                  ))}
                  {Object.keys(ops.batches.by_status).length === 0 && <span className="ui-muted">Aucun lot.</span>}
                </div>
              </Card>
            </>
          )}
        </div>
      )}

      {tab === "retention" && (
        <Card title="Rétention (RGPD)">
          <div className="ui-stack" style={{ maxWidth: 520 }}>
            <p className="ui-muted">
              Supprime définitivement les lots (et leurs verbatims/corrections + fichiers déposés)
              au-delà de la durée de rétention ({cfg?.retention_months ?? "—"} mois). Action irréversible.
            </p>
            <div><Button variant="danger" onClick={() => setConfirmPurge(true)}>Purger maintenant</Button></div>
          </div>
        </Card>
      )}

      {tab === "audit" && (
        <Card title="Journal d'audit (100 dernières actions)">
          {audit.length === 0 ? (
            <EmptyState title="Aucune entrée" description="Les actions tracées apparaîtront ici." />
          ) : (
            <div className="ui-table-wrap">
              <table className="ui-table">
                <thead>
                  <tr><th>Date</th><th>Utilisateur</th><th>Action</th><th>Cible</th><th>Détails</th></tr>
                </thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id}>
                      <td className="ui-mono" style={{ whiteSpace: "nowrap" }}>{a.created_at?.replace("T", " ").slice(0, 19)}</td>
                      <td>{a.user ?? "—"}</td>
                      <td><code>{a.action}</code></td>
                      <td>{a.entity ? `${a.entity}#${a.entity_id ?? ""}` : "—"}</td>
                      <td className="ui-muted">{a.details ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Dialog
        open={confirmPurge} danger busy={purging}
        title="Purger les données hors rétention ?"
        confirmLabel="Purger" cancelLabel="Annuler"
        onConfirm={doPurge} onCancel={() => setConfirmPurge(false)}
      >
        <p>Cette action supprime <b>définitivement</b> les lots au-delà de la rétention
          ({cfg?.retention_months ?? "—"} mois), avec leurs verbatims, corrections et fichiers. Elle est tracée dans l'audit.</p>
      </Dialog>
    </div>
  );
}
