import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getBatchKpi, listBatches, type Batch, type BatchKpi, type MetricComparison,
} from "../api";
import BarList from "../components/BarList";
import ClassificationEvolutionPanel from "../components/ClassificationEvolutionPanel";
import SatisfactionPanel from "../components/SatisfactionPanel";
import StackedSentimentBar from "../components/StackedSentimentBar";
import { Card, Chip, EmptyState, InfoTip, Select, Spinner, StatCard } from "../ui";

/**
 * Deux lectures d'une répartition de thèmes, jamais mélangées :
 *
 * * **principal** — un verbatim, une voix : son thème de tête. La somme fait le
 *   nombre de verbatims classés.
 * * **mentions** — thème principal ET second thème. La somme dépasse le nombre
 *   de verbatims, et c'est le seul angle qui rende visibles les sujets qui
 *   sortent presque toujours en second.
 *
 * Les afficher sous un seul chiffre ferait passer une somme supérieure au volume
 * du lot pour une erreur de comptage ; les garder séparés laisse la question
 * métier ouverte — « de quoi parle-t-on d'abord » n'est pas « de quoi parle-t-on ».
 */
type Angle = "principal" | "mentions";

export default function BatchKpiPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [kpi, setKpi] = useState<BatchKpi | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [referenceId, setReferenceId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [angle, setAngle] = useState<Angle>("mentions");

  useEffect(() => {
    setKpi(null);
    setError(null);
    const explicitReference = referenceId ? Number(referenceId) : undefined;
    getBatchKpi(batchId, explicitReference)
      .then(setKpi)
      .catch((e) => setError(String(e.message ?? e)));
  }, [batchId, referenceId]);

  useEffect(() => {
    listBatches().then(setBatches).catch(() => setBatches([]));
  }, []);

  if (error) return <EmptyState title="Tableau de bord indisponible" description={error} />;
  if (!kpi) return <Spinner label="Calcul des indicateurs…" />;

  const themes = angle === "mentions" ? kpi.themes_mentions : kpi.themes;
  const subthemes = angle === "mentions" ? kpi.subthemes_mentions : kpi.subthemes;
  const nMentions = Object.values(kpi.themes_mentions).reduce((a, b) => a + b, 0);
  const comparison = kpi.comparison;
  const referenceCandidates = batches.filter((batch) => batch.status === "done" && batch.id !== batchId);

  /** Les taux sont affichés en points de pourcentage, les volumes en unités. */
  const comparisonHint = (metric?: MetricComparison, suffix = "") => {
    if (!metric) return undefined;
    if (metric.comparable === false) return metric.reason ?? "Non comparable";
    const value = metric.unit === "ratio" ? metric.delta * 100 : metric.delta;
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toFixed(metric.unit === "ratio" ? 1 : 0)}${suffix} vs ${comparison?.reference_batch.label}`;
  };

  return (
    <div className="ui-stack">
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
                      hint={comparisonHint(comparison?.lot_metrics.review_rate, " pt")} />
            <StatCard label={<span className="ui-row" style={{ gap: 4 }}>Bi-thèmes<InfoTip text="Verbatims auxquels le modèle a retenu un second thème. Le taux est rapporté aux verbatims classés, pas au lot entier." /></span>}
                      value={kpi.n_bi_themes}
                      hint={comparisonHint(comparison?.lot_metrics.bi_theme_rate, " pt")
                        ?? `${(kpi.taux_bi_themes * 100).toFixed(1)} % des classés`} />
            <StatCard label="Rupture client" value={kpi.signals.rupture}
                      hint={comparisonHint(comparison?.lot_metrics.signal_rates.rupture, " pt")} />
            <StatCard label="Churn" value={kpi.signals.churn}
                      hint={comparisonHint(comparison?.lot_metrics.signal_rates.churn, " pt")} />
            <StatCard label={<span className="ui-row" style={{ gap: 4 }}>Insatisfaction forte<InfoTip text="Signal DÉDUIT par le modèle du texte du verbatim. À ne pas confondre avec la note déposée par le client." /></span>}
                      value={kpi.signals.insatisfaction}
                      hint={comparisonHint(comparison?.lot_metrics.signal_rates.insatisfaction, " pt")} />
            <StatCard label="Erreurs" value={kpi.n_errors} />
          </div>
        </Card>

        <Card title="Thèmes × sentiment (toutes mentions)"
              actions={<InfoTip text="Thème principal et second thème empilés, chacun avec SON sentiment : la V4 en calcule un par thème retenu, un même verbatim peut donc être positif sur la livraison et négatif sur le produit." />}>
          <StackedSentimentBar data={kpi.theme_sentiment} />
        </Card>

        <Card title="Répartition des thèmes" actions={
          <span className="ui-row" style={{ gap: 4 }}>
            <Chip active={angle === "principal"} onClick={() => setAngle("principal")}>Thème principal</Chip>
            <Chip active={angle === "mentions"} onClick={() => setAngle("mentions")}>Toutes mentions</Chip>
            <InfoTip text="« Thème principal » compte une voix par verbatim. « Toutes mentions » ajoute le second thème : la somme dépasse alors le nombre de verbatims, ce qui est normal." />
          </span>
        }>
          <div className="ui-stack">
            <p className="ui-muted">
              {angle === "mentions"
                ? `${nMentions} mention(s) de thème pour ${kpi.n_total} verbatim(s), dont ${kpi.n_bi_themes} bi-thème(s).`
                : `Thème de tête de chaque verbatim classé.`}
            </p>
            <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
              <Card title="Niveau 1"><BarList data={themes} /></Card>
              <Card title="Niveau 2 (sous-thèmes)"><BarList data={subthemes} color="var(--cu-primary-300)" /></Card>
            </div>
          </div>
        </Card>

        <Card title="Second thème seul"
              actions={<InfoTip text="Ce que la vue « thème principal » rend invisible : les sujets évoqués en appui, jamais en tête." />}>
          {kpi.n_bi_themes === 0 ? (
            <p className="ui-muted">Aucun verbatim de ce lot ne porte de second thème.</p>
          ) : (
            <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
              <Card title="Niveau 1"><BarList data={kpi.themes_secondaires} color="var(--cu-primary-300)" /></Card>
              <Card title="Niveau 2 (sous-thèmes)"><BarList data={kpi.subthemes_secondaires} color="var(--cu-primary-300)" /></Card>
            </div>
          )}
        </Card>

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
