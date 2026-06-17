import { useEffect, useState, type FormEvent } from "react";
import {
  getAudit, getConfig, patchConfig, purgeData,
  type AppConfigValues, type AuditEntry,
} from "../api";

export default function AdminPage() {
  const [cfg, setCfg] = useState<AppConfigValues | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [retention, setRetention] = useState("13");
  const [seuil, setSeuil] = useState("0.70");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    if (!confirm("Purger les lots au-delà de la rétention ? Cette action est irréversible.")) return;
    setMsg(null); setError(null);
    try {
      const r = await purgeData();
      setMsg(`Purge effectuée : ${r.batches} lot(s) supprimé(s).`);
      refresh();
    } catch (err: any) { setError(err?.message ?? "Erreur"); }
  };

  return (
    <div>
      <h1>Administration</h1>
      {msg && <p style={{ color: "green" }}>{msg}</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <section style={{ padding: "1rem 1.25rem", border: "1px solid #eee", borderRadius: 8, marginBottom: "2rem", maxWidth: 560 }}>
        <h3 style={{ marginTop: 0 }}>Configuration</h3>
        {!cfg && <p>Chargement…</p>}
        {cfg && (
          <form onSubmit={saveConfig} style={{ display: "grid", gap: "0.75rem" }}>
            <label>Rétention des données (mois)
              <input type="number" min={0} value={retention} onChange={(e) => setRetention(e.target.value)} style={{ marginLeft: 8, width: 80 }} />
            </label>
            <label>Seuil de revue par défaut
              <input type="number" min={0} max={1} step={0.05} value={seuil} onChange={(e) => setSeuil(e.target.value)} style={{ marginLeft: 8, width: 80 }} />
            </label>
            <div><button type="submit">Enregistrer</button></div>
          </form>
        )}
      </section>

      <section style={{ padding: "1rem 1.25rem", border: "1px solid #f0d0d0", borderRadius: 8, marginBottom: "2rem", maxWidth: 560 }}>
        <h3 style={{ marginTop: 0 }}>Rétention (RGPD)</h3>
        <p style={{ color: "#666" }}>Supprime définitivement les lots (et leurs verbatims) au-delà de la durée de rétention.</p>
        <button onClick={doPurge} style={{ color: "#b3261e" }}>Purger maintenant</button>
      </section>

      <section>
        <h3>Journal d'audit (100 dernières actions)</h3>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: ".85rem" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #ddd" }}>
              <th style={{ padding: "0.3rem" }}>Date</th><th>Utilisateur</th><th>Action</th><th>Cible</th><th>Détails</th>
            </tr>
          </thead>
          <tbody>
            {audit.map((a) => (
              <tr key={a.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "0.3rem", whiteSpace: "nowrap" }}>{a.created_at?.replace("T", " ").slice(0, 19)}</td>
                <td>{a.user ?? "—"}</td>
                <td><code>{a.action}</code></td>
                <td>{a.entity ? `${a.entity}#${a.entity_id ?? ""}` : "—"}</td>
                <td style={{ color: "#666" }}>{a.details ?? ""}</td>
              </tr>
            ))}
            {audit.length === 0 && <tr><td colSpan={5} style={{ color: "#888", padding: "0.5rem" }}>Aucune entrée.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
