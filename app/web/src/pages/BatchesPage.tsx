import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createBatch, listBatches, type Batch } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function BatchesPage() {
  const navigate = useNavigate();
  const [batches, setBatches] = useState<Batch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [seuil, setSeuil] = useState(0.7);
  const mdtcRef = useRef<HTMLInputElement>(null);
  const mopinionRef = useRef<HTMLInputElement>(null);

  const refresh = () => listBatches().then(setBatches).catch((e) => setError(String(e.message ?? e)));

  useEffect(() => {
    refresh();
    // Rafraîchit tant qu'un lot est en cours.
    const t = setInterval(() => {
      setBatches((prev) => {
        if (prev.some((b) => b.status === "pending" || b.status === "running")) refresh();
        return prev;
      });
    }, 3000);
    return () => clearInterval(t);
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const mdtc = mdtcRef.current?.files?.[0] ?? null;
    const mopinion = mopinionRef.current?.files?.[0] ?? null;
    if (!mdtc && !mopinion) {
      setError("Sélectionnez au moins un fichier (MDTC ou Mopinion).");
      return;
    }
    setBusy(true);
    try {
      const b = await createBatch({ label: label.trim() || undefined, seuilRevue: seuil, mdtc, mopinion });
      navigate(`/lots/${b.id}`);
    } catch (err: any) {
      setError(err?.message ?? "Erreur lors de la création du lot");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1>Lots de traitement</h1>

      <section style={{ padding: "1rem 1.25rem", border: "1px solid #eee", borderRadius: 8, marginBottom: "2rem" }}>
        <h3 style={{ marginTop: 0 }}>Nouveau lot</h3>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
        <form onSubmit={onSubmit} style={{ display: "grid", gap: "0.75rem", maxWidth: 560 }}>
          <label>Fichier MDTC (.xlsx) <input type="file" accept=".xlsx" ref={mdtcRef} /></label>
          <label>Fichier Mopinion (.xlsx) <input type="file" accept=".xlsx" ref={mopinionRef} /></label>
          <label>Libellé du lot
            <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="ex. juillet 2026" style={{ marginLeft: 8 }} />
          </label>
          <label>Seuil de revue humaine ({seuil.toFixed(2)})
            <input type="range" min={0} max={1} step={0.05} value={seuil}
                   onChange={(e) => setSeuil(parseFloat(e.target.value))} style={{ marginLeft: 8, verticalAlign: "middle" }} />
          </label>
          <div><button type="submit" disabled={busy}>{busy ? "Lancement…" : "Lancer le traitement"}</button></div>
        </form>
      </section>

      <h3>Historique</h3>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #ddd" }}>
            <th style={{ padding: "0.4rem" }}>#</th><th>Libellé</th><th>Statut</th>
            <th>Progression</th><th>Verbatims</th><th>Revue</th><th>Modèle</th>
          </tr>
        </thead>
        <tbody>
          {batches.length === 0 && <tr><td colSpan={7} style={{ padding: "0.6rem", color: "#888" }}>Aucun lot pour l'instant.</td></tr>}
          {batches.map((b) => {
            const pct = b.n_total ? Math.round((b.n_processed / b.n_total) * 100) : 0;
            return (
              <tr key={b.id} onClick={() => navigate(`/lots/${b.id}`)}
                  style={{ borderBottom: "1px solid #eee", cursor: "pointer" }}>
                <td style={{ padding: "0.4rem" }}>{b.id}</td>
                <td>{b.label}</td>
                <td><StatusBadge status={b.status} /></td>
                <td>{b.status === "running" || b.status === "pending" ? `${pct}%` : "—"}</td>
                <td>{b.n_total || "—"}</td>
                <td>{b.status === "done" ? b.n_review : "—"}</td>
                <td style={{ color: "#666", fontSize: ".85rem" }}>{b.model_label ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
