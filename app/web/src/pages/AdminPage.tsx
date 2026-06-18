import { useEffect, useState, type FormEvent } from "react";
import {
  getAudit, getConfig, patchConfig, purgeData,
  type AppConfigValues, type AuditEntry,
} from "../api";
import { Button, Card, Dialog, EmptyState, Input } from "../ui";

type Tab = "config" | "retention" | "audit";

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("config");
  const [cfg, setCfg] = useState<AppConfigValues | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [retention, setRetention] = useState("13");
  const [seuil, setSeuil] = useState("0.70");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [purging, setPurging] = useState(false);

  const refresh = () => {
    getConfig().then((c) => { setCfg(c); setRetention(c.retention_months); setSeuil(c.default_seuil_revue); })
      .catch((e) => setError(String(e.message ?? e)));
    getAudit(100).then(setAudit).catch(() => setAudit([]));
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
