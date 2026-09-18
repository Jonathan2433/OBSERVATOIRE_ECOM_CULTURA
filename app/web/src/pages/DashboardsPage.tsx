import { useEffect, useState } from "react";
import {
  getBatchKpi, getModelKpi, getVolumetry, type BatchKpi, type ModelKpi, type Volumetry,
} from "../api";
import BarList from "../components/BarList";
import ClassificationEvolutionPanel from "../components/ClassificationEvolutionPanel";
import SatisfactionPanel from "../components/SatisfactionPanel";
import StackedSentimentBar from "../components/StackedSentimentBar";
import ThemeDistributionPanel from "../components/ThemeDistributionPanel";
import { Badge, Card, EmptyState, InfoTip, Spinner, StatCard } from "../ui";
import { useAnalysisFilters } from "../analysisFilters";
import AnalysisFiltersBar from "../components/AnalysisFiltersBar";

const METRIC_LABELS: Record<string, string> = {
  f1_macro_niv1: "F1-macro niv.1",
  f1_macro_niv2: "F1-macro niv.2",
  accuracy_sentiment: "Accuracy sentiment",
  f1_macro_sentiment: "F1-macro sentiment",
  recall_rupture: "Rappel rupture",
};
// Seuils cibles (cahier §6.1). Défaut 0,70 pour les métriques connues.
//
// Chaque moteur ne publie que les métriques VALIDEMENT mesurées sur le jeu de
// test gelé : le moteur V1 n'expose que le sentiment, faute d'évaluation
// thématique fiable (celle du 18/06 portait sur un découpage fuité à 99,6 %).
// Une case absente veut donc dire « non mesuré », jamais « zéro ».
const SEUILS: Record<string, number> = {
  f1_macro_niv1: 0.70, f1_macro_niv2: 0.55, accuracy_sentiment: 0.70,
  f1_macro_sentiment: 0.60, recall_rupture: 0.60,
};

export default function DashboardsPage() {
  const [model, setModel] = useState<ModelKpi | null>(null);
  const [vol, setVol] = useState<Volumetry | null>(null);
  const [latest, setLatest] = useState<BatchKpi | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { filters: analysisFilters, setFilters: setAnalysisFilters } = useAnalysisFilters();

  useEffect(() => {
    getModelKpi().then(setModel).catch((e) => setError(String(e.message ?? e)));
    setError(null);
    setVol(null);
    setLatest(null);
    getVolumetry(analysisFilters).then((data) => {
      setVol(data);
      const latestBatch = data.series[data.series.length - 1];
      if (latestBatch) {
        getBatchKpi(latestBatch.id, undefined, analysisFilters).then(setLatest)
          .catch((e) => setError(String(e.message ?? e)));
      }
    }).catch((e) => setError(String(e.message ?? e)));
  }, [analysisFilters]);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Tableaux de bord</h1>
        <p className="page-header__sub">Notes déclarées, analyse des textes libres et performance du modèle actif.</p>
      </div>

      {error && <p className="ui-field__error">{error}</p>}

      <div className="ui-stack">
        <AnalysisFiltersBar filters={analysisFilters} onChange={setAnalysisFilters} />
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
              <StatCard label={<span className="ui-row" style={{ gap: 4 }}>Bi-thèmes<InfoTip text="Verbatims auxquels le modèle a retenu un second thème, tous lots confondus." /></span>}
                        value={vol.n_bi_themes} />
            </div>

            {vol.series.length > 0 && !latest && <Spinner label="Chargement de la synthèse métier…" />}
            {latest && (
              <>
                <SatisfactionPanel
                  sat={latest.satisfaction}
                  titre={`Satisfaction client — ${latest.label}`}
                  comparison={latest.comparison?.satisfaction}
                  referenceLabel={latest.comparison?.reference_batch.label}
                />
                <ClassificationEvolutionPanel
                  evolution={latest.classification_evolution}
                  referenceLabel={latest.comparison?.reference_batch.label}
                />
              </>
            )}

            <Card title="Thèmes × sentiment (volumétrie globale)"
                  actions={<InfoTip text="Thème principal et second thème empilés, chacun avec son propre sentiment. Sélectionnez un thème pour déplier ses sous-thèmes." />}>
              <StackedSentimentBar
                data={vol.theme_sentiment}
                hierarchy={vol.theme_sentiment_hierarchy}
              />
            </Card>

            <ThemeDistributionPanel
              totalVerbatims={vol.total_verbatims}
              nBiThemes={vol.n_bi_themes}
              principal={{
                themes: vol.global_themes,
                subthemes: vol.global_subthemes,
                hierarchy: vol.global_theme_hierarchy.principal,
                sentiment: vol.theme_sentiment_views.principal,
              }}
              mentions={{
                themes: vol.global_themes_mentions,
                subthemes: vol.global_subthemes_mentions,
                hierarchy: vol.global_theme_hierarchy.mentions,
                sentiment: vol.theme_sentiment_views.mentions,
              }}
              secondary={{
                themes: vol.global_themes_secondaires,
                subthemes: vol.global_subthemes_secondaires,
                hierarchy: vol.global_theme_hierarchy.secondaire,
                sentiment: vol.theme_sentiment_views.secondaire,
              }}
            />

            <Card title="Sources des verbatims"
                  actions={<InfoTip text="Répartition recalculée selon les sources et dates sélectionnées." />}>
              <BarList data={vol.global_sources} color="var(--cu-neutral-300)" />
            </Card>

            <Card title="Évolution par lot">
              {vol.series.length === 0 ? (
                <EmptyState title="Aucun lot terminé" description="Les tendances apparaîtront après le premier traitement." />
              ) : (
                <div className="ui-table-wrap">
                  <table className="ui-table">
                    <thead>
                      <tr><th>Lot</th><th>Verbatims</th><th>Taux revue</th><th>Bi-thèmes</th><th>Rupture</th><th>Churn</th><th>Insatisf. forte</th></tr>
                    </thead>
                    <tbody>
                      {vol.series.map((s) => (
                        <tr key={s.id}>
                          <td>{s.label}</td>
                          <td className="ui-table__num">{s.n_total}</td>
                          <td className="ui-table__num">{(s.review_rate * 100).toFixed(1)} %</td>
                          <td className="ui-table__num">{s.n_bi_themes}</td>
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
