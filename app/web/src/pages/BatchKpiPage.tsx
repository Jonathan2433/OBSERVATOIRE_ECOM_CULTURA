import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getBatchKpi, listBatches, type Batch, type BatchKpi, type MetricComparison,
} from "../api";
import BarList from "../components/BarList";
import ClassificationEvolutionPanel from "../components/ClassificationEvolutionPanel";
import SatisfactionPanel from "../components/SatisfactionPanel";
import StackedSentimentBar from "../components/StackedSentimentBar";
import ThemeDistributionPanel from "../components/ThemeDistributionPanel";
import { formatEvolutionPercent, relativeEvolution } from "../evolutionDisplay";
import { Card, EmptyState, InfoTip, Select, Spinner, StatCard } from "../ui";
import { useAnalysisFilters } from "../analysisFilters";
import AnalysisFiltersBar from "../components/AnalysisFiltersBar";

export default function BatchKpiPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [kpi, setKpi] = useState<BatchKpi | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [referenceId, setReferenceId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { filters: analysisFilters, setFilters: setAnalysisFilters } = useAnalysisFilters();

  useEffect(() => {
    setKpi(null);
    setError(null);
    const explicitReference = referenceId ? Number(referenceId) : undefined;
    getBatchKpi(batchId, explicitReference, analysisFilters)
      .then(setKpi)
      .catch((e) => setError(String(e.message ?? e)));
  }, [batchId, referenceId, analysisFilters]);

  useEffect(() => {
    listBatches().then(setBatches).catch(() => setBatches([]));
  }, []);

  if (error) return <EmptyState title="Tableau de bord indisponible" description={error} />;
  if (!kpi) return <Spinner label="Calcul des indicateurs…" />;

  const comparison = kpi.comparison;
  const referenceCandidates = batches.filter((batch) => batch.status === "done" && batch.id !== batchId);

  /** Les taux sont affichés en évolution relative (%), les volumes en delta absolu. */
  const comparisonHint = (metric?: MetricComparison) => {
    if (!metric) return undefined;
    if (metric.comparable === false) return metric.reason ?? "Non comparable";
    const refLabel = comparison?.reference_batch.label;
    if (metric.unit === "count") {
      const sign = metric.delta > 0 ? "+" : "";
      return `${sign}${metric.delta.toFixed(0)} vs ${refLabel}`;
    }
    const outcome = relativeEvolution(metric.current, metric.reference, true);
    return `${formatEvolutionPercent(outcome)} vs ${refLabel}`;
  };

  return (
    <div className="ui-stack">
        <AnalysisFiltersBar filters={analysisFilters} onChange={setAnalysisFilters} />
        <section className="business-overview">
          <div className="business-overview__copy">
            <p className="business-section__eyebrow">Synthèse de la période</p>
            <h2>Satisfaction déclarée et analyse des verbatims</h2>
            <p className="ui-muted">
              Les notes cochées et les textes libres sont présentés séparément, par source.
              Les analyses techniques détaillées restent disponibles plus bas.
            </p>
          </div>
          <div className="business-overview__picker">
            <Select
              label="Comparer ce lot à"
              value={referenceId}
              onChange={(event) => setReferenceId(event.target.value)}
              hint="Par défaut, l’application choisit le dernier lot terminé dont la période métier précède celle-ci."
            >
              <option value="">Sélection automatique</option>
              {referenceCandidates.map((batch) => (
                <option key={batch.id} value={batch.id}>#{batch.id} — {batch.label}</option>
              ))}
            </Select>
            {!comparison && (
              <p className="ui-field__hint">
                Aucun lot antérieur non chevauchant avec une période métier exploitable.
              </p>
            )}
          </div>
        </section>

        <SatisfactionPanel
          sat={kpi.satisfaction}
          comparison={comparison?.satisfaction}
          referenceLabel={comparison?.reference_batch.label}
        />

        <ClassificationEvolutionPanel
          evolution={kpi.classification_evolution}
          referenceLabel={comparison?.reference_batch.label}
        />

        <Card title="Indicateurs techniques du lot"
              actions={<InfoTip text="Ces indicateurs décrivent le traitement et les sorties du modèle. Ils sont séparés des notes déclarées par les clients." />}>
          <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
            <StatCard label="Verbatims" value={kpi.n_total}
                      hint={comparisonHint(comparison?.lot_metrics.volume)} />
            <StatCard label="Taux de revue" value={`${(kpi.review_rate * 100).toFixed(1)} %`}
                      hint={comparisonHint(comparison?.lot_metrics.review_rate)} />
            <StatCard label={<span className="ui-row" style={{ gap: 4 }}>Bi-thèmes<InfoTip text="Verbatims auxquels le modèle a retenu un second thème. Le taux est rapporté aux verbatims classés, pas au lot entier." /></span>}
                      value={kpi.n_bi_themes}
                      hint={comparisonHint(comparison?.lot_metrics.bi_theme_rate)
                        ?? `${(kpi.taux_bi_themes * 100).toFixed(1)} % des classés`} />
            <StatCard label="Rupture client" value={kpi.signals.rupture}
                      hint={comparisonHint(comparison?.lot_metrics.signal_rates.rupture)} />
            <StatCard label="Churn" value={kpi.signals.churn}
                      hint={comparisonHint(comparison?.lot_metrics.signal_rates.churn)} />
            <StatCard label={<span className="ui-row" style={{ gap: 4 }}>Insatisfaction forte<InfoTip text="Signal DÉDUIT par le modèle du texte du verbatim. À ne pas confondre avec la note déposée par le client." /></span>}
                      value={kpi.signals.insatisfaction}
                      hint={comparisonHint(comparison?.lot_metrics.signal_rates.insatisfaction)} />
            <StatCard label="Erreurs" value={kpi.n_errors} />
          </div>
        </Card>

        <Card title="Thèmes × sentiment (toutes mentions)"
              actions={<InfoTip text="Thème principal et second thème empilés, chacun avec SON sentiment. Sélectionnez un thème pour déplier ses sous-thèmes et leur propre répartition." />}>
          <StackedSentimentBar
            data={kpi.theme_sentiment}
            hierarchy={kpi.theme_sentiment_hierarchy}
          />
        </Card>

        <ThemeDistributionPanel
          totalVerbatims={kpi.n_total}
          nBiThemes={kpi.n_bi_themes}
          principal={{
            themes: kpi.themes,
            subthemes: kpi.subthemes,
            hierarchy: kpi.theme_hierarchy.principal,
            sentiment: kpi.theme_sentiment_views.principal,
          }}
          mentions={{
            themes: kpi.themes_mentions,
            subthemes: kpi.subthemes_mentions,
            hierarchy: kpi.theme_hierarchy.mentions,
            sentiment: kpi.theme_sentiment_views.mentions,
          }}
          secondary={{
            themes: kpi.themes_secondaires,
            subthemes: kpi.subthemes_secondaires,
            hierarchy: kpi.theme_hierarchy.secondaire,
            sentiment: kpi.theme_sentiment_views.secondaire,
          }}
        />

        <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
          <Card title="Sentiments (thème principal)"><BarList data={kpi.sentiments} /></Card>
          <Card title="Sentiments (second thème)">
            {kpi.n_bi_themes === 0
              ? <p className="ui-muted">Aucun second thème.</p>
              : <BarList data={kpi.sentiments_secondaires} color="var(--cu-primary-300)" />}
          </Card>
          <Card title="Sources"><BarList data={kpi.sources} color="var(--cu-primary-300)" /></Card>
        </div>
    </div>
  );
}
