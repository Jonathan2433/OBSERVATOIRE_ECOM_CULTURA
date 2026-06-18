import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getBatchKpi, type BatchKpi } from "../api";
import BarList from "../components/BarList";
import StackedSentimentBar from "../components/StackedSentimentBar";
import { Card, EmptyState, Spinner, StatCard } from "../ui";

export default function BatchKpiPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [kpi, setKpi] = useState<BatchKpi | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBatchKpi(batchId).then(setKpi).catch((e) => setError(String(e.message ?? e)));
  }, [batchId]);

  if (error) return <EmptyState title="Tableau de bord indisponible" description={error} />;
  if (!kpi) return <Spinner label="Calcul des indicateurs…" />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Tableau de bord — lot #{batchId}</h1>
        <p className="page-header__sub">« {kpi.label} » · modèle : {kpi.model_label ?? "—"}</p>
      </div>

      <div className="ui-stack">
        <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
          <StatCard label="Verbatims" value={kpi.n_total} />
          <StatCard label="Taux de revue" value={`${(kpi.review_rate * 100).toFixed(1)} %`} />
          <StatCard label="Rupture client" value={kpi.signals.rupture} />
          <StatCard label="Churn" value={kpi.signals.churn} />
          <StatCard label="Insatisfaction" value={kpi.signals.insatisfaction} />
          <StatCard label="Erreurs" value={kpi.n_errors} />
        </div>

        <Card title="Thèmes × sentiment (volumétrie)">
          <StackedSentimentBar data={kpi.theme_sentiment} />
        </Card>

        <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
          <Card title="Thèmes (niv.1)"><BarList data={kpi.themes} /></Card>
          <Card title="Sentiments"><BarList data={kpi.sentiments} /></Card>
          <Card title="Sources"><BarList data={kpi.sources} color="var(--cu-primary-300)" /></Card>
        </div>
      </div>
    </div>
  );
}
