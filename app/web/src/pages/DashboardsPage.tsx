import { useEffect, useState } from "react";
import { getModelKpi, getVolumetry, type ModelKpi, type Volumetry } from "../api";
import BarList from "../components/BarList";
import StackedSentimentBar from "../components/StackedSentimentBar";
import { Badge, Card, EmptyState, Spinner, StatCard } from "../ui";

const METRIC_LABELS: Record<string, string> = {
  f1_macro_niv1: "F1-macro niv.1",
  f1_macro_niv2: "F1-macro niv.2",
  accuracy_sentiment: "Accuracy sentiment",
  recall_rupture: "Rappel rupture",
};
// Seuils cibles (cahier §6.1). Défaut 0,70 pour les métriques connues.
const SEUILS: Record<string, number> = {
  f1_macro_niv1: 0.70, f1_macro_niv2: 0.55, accuracy_sentiment: 0.70, recall_rupture: 0.60,
};

export default function DashboardsPage() {
  const [model, setModel] = useState<ModelKpi | null>(null);
  const [vol, setVol] = useState<Volumetry | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getModelKpi().then(setModel).catch((e) => setError(String(e.message ?? e)));
    getVolumetry().then(setVol).catch((e) => setError(String(e.message ?? e)));
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Tableaux de bord</h1>
        <p className="page-header__sub">Performance du modèle actif et volumétrie globale des lots traités.</p>
      </div>

      {error && <p className="ui-field__error">{error}</p>}

      <div className="ui-stack">
        <Card title="Modèle actif">
          {!model && <Spinner label="Chargement…" />}
          {model && model.active === null && <p className="ui-muted">Aucun modèle actif.</p>}
          {model && model.active && (
            <div className="ui-stack">
              <div className="ui-row ui-row--wrap">
                <Badge tone="primary">{model.active.label}</Badge>
                <Badge tone={model.active.kind === "real" ? "success" : "neutral"}>{model.active.kind}</Badge>
                {model.active.kind === "stub" && (
                  <span className="ui-muted">Modèle de démonstration (heuristique) — entraînez et déposez un CamemBERT pour les KPI qualité.</span>
                )}
              </div>
              {model.active.metrics && Object.keys(model.active.metrics).length > 0 && (
                <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))" }}>
                  {Object.entries(model.active.metrics).map(([k, v]) => {
                    const num = typeof v === "number" ? v : Number(v);
                    const seuil = SEUILS[k];
                    const below = seuil != null && Number.isFinite(num) && num < seuil;
                    return (
                      <StatCard key={k} label={METRIC_LABELS[k] ?? k}
                        value={<span className="ui-row" style={{ gap: 8 }}>
                          {Number.isFinite(num) ? num.toFixed(3) : String(v)}
                          {seuil != null && (below ? <Badge tone="danger">sous seuil</Badge> : <Badge tone="success">OK</Badge>)}
                        </span>}
                        hint={seuil != null ? `cible ≥ ${seuil.toFixed(2)}` : undefined} />
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </Card>

        {!vol && <Spinner label="Chargement de la volumétrie…" />}
        {vol && (
          <>
            <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
              <StatCard label="Lots traités" value={vol.n_batches} />
              <StatCard label="Verbatims (total)" value={vol.total_verbatims} />
            </div>

            <Card title="Thèmes × sentiment (volumétrie globale)">
              <StackedSentimentBar data={vol.theme_sentiment} />
            </Card>

            <Card title="Répartition globale des thèmes">
              <BarList data={vol.global_themes} />
            </Card>

            <Card title="Évolution par lot">
              {vol.series.length === 0 ? (
                <EmptyState title="Aucun lot terminé" description="Les tendances apparaîtront après le premier traitement." />
              ) : (
                <div className="ui-table-wrap">
                  <table className="ui-table">
                    <thead>
                      <tr><th>Lot</th><th>Verbatims</th><th>Taux revue</th><th>Rupture</th><th>Churn</th><th>Insatisf.</th></tr>
                    </thead>
                    <tbody>
                      {vol.series.map((s) => (
                        <tr key={s.id}>
                          <td>{s.label}</td>
                          <td className="ui-table__num">{s.n_total}</td>
                          <td className="ui-table__num">{(s.review_rate * 100).toFixed(1)} %</td>
                          <td className="ui-table__num">{s.signals.rupture}</td>
                          <td className="ui-table__num">{s.signals.churn}</td>
                          <td className="ui-table__num">{s.signals.insatisfaction}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
