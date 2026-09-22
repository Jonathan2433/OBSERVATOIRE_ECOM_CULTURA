import { useEffect, useState } from "react";
import {
  getBatchKpi, getVolumetry, type BatchKpi, type Volumetry,
} from "../api";
import BarList from "../components/BarList";
import ClassificationEvolutionPanel from "../components/ClassificationEvolutionPanel";
import SatisfactionPanel from "../components/SatisfactionPanel";
import StackedSentimentBar from "../components/StackedSentimentBar";
import ThemeDistributionPanel from "../components/ThemeDistributionPanel";
import { Card, EmptyState, InfoTip, Spinner, StatCard } from "../ui";
import { useAnalysisFilters } from "../analysisFilters";
import AnalysisFiltersBar from "../components/AnalysisFiltersBar";

export default function DashboardsPage() {
  const [vol, setVol] = useState<Volumetry | null>(null);
  const [latest, setLatest] = useState<BatchKpi | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { filters: analysisFilters, setFilters: setAnalysisFilters } = useAnalysisFilters();

  useEffect(() => {
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
        <p className="page-header__sub">Notes déclarées et analyse des textes libres, agrégées sur les lots terminés.</p>
      </div>

      {error && <p className="ui-field__error">{error}</p>}

      <div className="ui-stack">
        <AnalysisFiltersBar filters={analysisFilters} onChange={setAnalysisFilters} />

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
