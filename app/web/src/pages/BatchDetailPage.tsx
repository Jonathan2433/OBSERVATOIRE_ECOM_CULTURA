import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getBatch, type Batch } from "../api";
import StatusBadge from "../components/StatusBadge";

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div style={{ background: "#eee", borderRadius: 6, height: 14, overflow: "hidden", maxWidth: 420 }}>
      <div style={{ width: `${pct}%`, background: "#0b5cad", height: "100%", transition: "width .3s" }} />
    </div>
  );
}

export default function BatchDetailPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const b = await getBatch(batchId);
        if (!active) return;
        setBatch(b);
        if (b.status === "pending" || b.status === "running") timer = setTimeout(tick, 1500);
      } catch (e: any) {
        if (active) setError(e?.message ?? "Erreur");
      }
    };
    tick();
    return () => { active = false; clearTimeout(timer); };
  }, [batchId]);

  if (error) return <p style={{ color: "crimson" }}>{error} — <Link to="/lots">retour</Link></p>;
  if (!batch) return <p>Chargement…</p>;

  const pct = batch.n_total ? Math.round((batch.n_processed / batch.n_total) * 100) : 0;
  const running = batch.status === "pending" || batch.status === "running";

  return (
    <div>
      <p><Link to="/lots">← Lots</Link></p>
      <h1>Lot #{batch.id} — {batch.label} <StatusBadge status={batch.status} /></h1>

      {running && (
        <section style={{ margin: "1.5rem 0" }}>
          <p>Traitement en cours… {batch.n_processed} / {batch.n_total || "?"} ({pct}%)</p>
          <ProgressBar pct={pct} />
        </section>
      )}

      {batch.status === "failed" && (
        <p style={{ color: "crimson" }}><b>Échec :</b> {batch.error_message || "erreur inconnue"}</p>
      )}

      <section style={{ marginTop: "1.5rem", padding: "1rem 1.25rem", border: "1px solid #eee", borderRadius: 8 }}>
        <h3 style={{ marginTop: 0 }}>Résumé</h3>
        <table>
          <tbody>
            <tr><td style={{ padding: "0.2rem 1rem 0.2rem 0", color: "#666" }}>Modèle utilisé</td><td>{batch.model_label ?? "—"}</td></tr>
            <tr><td style={{ color: "#666" }}>Seuil de revue</td><td>{batch.seuil_revue.toFixed(2)}</td></tr>
            <tr><td style={{ color: "#666" }}>Verbatims traités</td><td>{batch.n_total}</td></tr>
            <tr><td style={{ color: "#666" }}>En revue humaine</td><td>{batch.status === "done" ? `${batch.n_review} (${batch.n_total ? Math.round((batch.n_review / batch.n_total) * 100) : 0}%)` : "—"}</td></tr>
            <tr><td style={{ color: "#666" }}>Erreurs</td><td>{batch.n_errors}</td></tr>
            <tr><td style={{ color: "#666" }}>Durée</td><td>{batch.duration_s != null ? `${batch.duration_s.toFixed(1)} s` : "—"}</td></tr>
          </tbody>
        </table>
      </section>

      {batch.status === "done" && (
        <p style={{ marginTop: "1.5rem", display: "flex", gap: "1.5rem" }}>
          <Link to={`/lots/${batch.id}/resultats`}>→ Consulter et exporter les résultats</Link>
          <Link to={`/lots/${batch.id}/revue`}>→ Revue humaine ({batch.n_review})</Link>
        </p>
      )}
    </div>
  );
}
