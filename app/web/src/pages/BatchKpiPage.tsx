import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getBatchKpi, type BatchKpi } from "../api";
import BarList from "../components/BarList";
import StackedSentimentBar from "../components/StackedSentimentBar";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid #eee", borderRadius: 8, padding: "0.75rem 1rem", minWidth: 130 }}>
      <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{value}</div>
      <div style={{ color: "#666", fontSize: ".85rem" }}>{label}</div>
    </div>
  );
}

export default function BatchKpiPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [kpi, setKpi] = useState<BatchKpi | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBatchKpi(batchId).then(setKpi).catch((e) => setError(String(e.message ?? e)));
  }, [batchId]);

  if (error) return <p style={{ color: "crimson" }}>{error} — <Link to={`/lots/${batchId}`}>retour</Link></p>;
  if (!kpi) return <p>Chargement…</p>;

  return (
    <div>
      <p><Link to={`/lots/${batchId}`}>← Lot #{batchId}</Link></p>
      <h1>Tableau de bord — lot #{batchId} « {kpi.label} »</h1>

      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", margin: "1rem 0 2rem" }}>
        <Stat label="Verbatims" value={String(kpi.n_total)} />
        <Stat label="Taux de revue" value={`${(kpi.review_rate * 100).toFixed(1)}%`} />
        <Stat label="Rupture client" value={String(kpi.signals.rupture)} />
        <Stat label="Churn" value={String(kpi.signals.churn)} />
        <Stat label="Insatisfaction" value={String(kpi.signals.insatisfaction)} />
        <Stat label="Erreurs" value={String(kpi.n_errors)} />
      </div>

      <h3>Thèmes (niv.1)</h3>
      <BarList data={kpi.themes} />

      <h3 style={{ marginTop: "2rem" }}>Thèmes × sentiment (volumétrie)</h3>
      <StackedSentimentBar data={kpi.theme_sentiment} />

      <h3 style={{ marginTop: "2rem" }}>Sentiments</h3>
      <BarList data={kpi.sentiments} color="#7a5cad" />

      <h3 style={{ marginTop: "2rem" }}>Sources</h3>
      <BarList data={kpi.sources} color="#1a7f37" />

      <p style={{ marginTop: "2rem", color: "#888", fontSize: ".85rem" }}>
        Modèle utilisé : {kpi.model_label ?? "—"}
      </p>
    </div>
  );
}
