import type {
  ClassificationEvolution, ClassificationEvolutionItem, ClassificationSourceEvolution,
} from "../api";
import { DASHBOARD_SOURCE_GROUPS } from "../dashboardSources";
import { formatEvolutionPercent, relativeEvolution } from "../evolutionDisplay";
import { SOURCE_LABELS, SOURCE_SHORT_LABELS } from "../satisfactionDisplay";
import { Badge, Card, InfoTip } from "../ui";

function EvolutionBadge({ item, comparable }: {
  item: ClassificationEvolutionItem;
  comparable: boolean;
}) {
  const outcome = relativeEvolution(item.current_share, item.reference_share, comparable);
  if (outcome.kind === "not-comparable") {
    return <Badge tone="neutral">non comparable</Badge>;
  }
  if (outcome.kind === "new") {
    return <Badge tone="warning">nouveau</Badge>;
  }
  const tone = outcome.kind === "value"
    ? (outcome.percent > 0 ? "warning" : outcome.percent < 0 ? "success" : "neutral")
    : "neutral";
  return <Badge tone={tone}>{formatEvolutionPercent(outcome)}</Badge>;
}

function SourceRanking({ source, showComparison }: {
  source: ClassificationSourceEvolution;
  showComparison: boolean;
}) {
  return (
    <section className="classification-source">
      <div className="classification-source__header">
        <h4>{SOURCE_SHORT_LABELS[source.source_type] ?? SOURCE_LABELS[source.source_type] ?? source.source_type}</h4>
        <span>{source.current_verbatim_count.toLocaleString("fr-FR")} verbatim(s)</span>
      </div>
      {source.items.length === 0 ? (
        <p className={source.availability_status === "source_not_provided"
          ? "business-empty-source" : "ui-muted"}>
          {source.availability_status === "source_not_provided"
            ? "Aucune donnée reçue pour cette source dans ce lot."
            : "Aucun sous-thème disponible."}
        </p>
      ) : (
        <ol className="classification-ranking">
          {source.items.map((item) => (
            <li key={`${item.niv1}\u0000${item.niv2 ?? ""}`} className="classification-ranking__item">
              <span className="classification-ranking__rank" aria-label={`Rang ${item.current_rank}`}>
                {item.current_rank}
              </span>
              <span className="classification-ranking__label">
                <strong>{item.label}</strong>
                {item.niv2 && <small>{item.niv1}</small>}
              </span>
              <span className="classification-ranking__metric">
                <strong>{item.current_count.toLocaleString("fr-FR")}</strong>
                <small>{(item.current_share * 100).toFixed(1)} %</small>
              </span>
              <span className="classification-ranking__trend">
                {showComparison && <EvolutionBadge item={item} comparable={source.comparable} />}
                {showComparison && source.comparable && item.rank_delta != null && item.rank_delta !== 0 && (
                  <small>{item.rank_delta > 0 ? "↑" : "↓"} {Math.abs(item.rank_delta)} rang(s)</small>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
      {showComparison && !source.comparable && source.reason && (
        <p className="classification-source__reason">{source.reason}</p>
      )}
    </section>
  );
}

/** Top sous-thèmes par source, au sein de tous les verbatims de la source. */
export default function ClassificationEvolutionPanel({
  evolution, referenceLabel,
}: {
  evolution: ClassificationEvolution;
  referenceLabel?: string | null;
}) {
  const rows = evolution.levels.niv2;
  const knownSources = new Set(DASHBOARD_SOURCE_GROUPS.flatMap((group) => group.sources));
  const historicalGroups = rows
    .filter((source) => !knownSources.has(source.source_type))
    .map((source) => ({
      key: `other-${source.source_type}`,
      title: SOURCE_LABELS[source.source_type] ?? source.source_type,
      sources: [source.source_type],
    }));
  const groups = [...DASHBOARD_SOURCE_GROUPS, ...historicalGroups]
    .map((group) => ({
      ...group,
      rows: group.sources
        .map((source) => rows.find((item) => item.source_type === source))
        .filter((source): source is ClassificationSourceEvolution => source != null),
    }))
    .filter((group) => group.rows.length > 0);

  return (
    <section className="business-section" aria-labelledby="classification-evolution-title">
      <div className="business-section__header">
        <div>
          <p className="business-section__eyebrow">Questions ouvertes</p>
          <h2 id="classification-evolution-title">Analyse automatique des verbatims</h2>
          <p className="ui-muted">
            Top sous-thèmes issus des textes libres, toutes mentions confondues.
            Les réponses aux questions fermées ne sont pas incluses.
            {referenceLabel ? ` Évolution comparée à ${referenceLabel}.` : " Aucune référence comparable."}
          </p>
        </div>
        <InfoTip text="Le nombre indique les verbatims de la source qui mentionnent la classification. Le thème principal et le second thème sont comptés. Un verbatim bi-thème peut apparaître dans deux classifications, mais jamais deux fois dans la même. Les choix des questions fermées ne participent pas à ce classement." />
      </div>

      {!evolution.comparable && evolution.reason && (
        <p className="business-notice">{evolution.reason} Les volumes courants restent affichés.</p>
      )}

      {groups.length === 0 ? (
        <Card><p className="ui-muted">Aucune classification disponible sur ce lot.</p></Card>
      ) : (
        <div className="business-card-grid">
          {groups.map((group) => (
            <article key={group.key} className="business-card classification-card">
              <header className="business-card__header">
                <h3>{group.title}</h3>
                <Badge tone="primary">Top {evolution.top_n}</Badge>
              </header>
              <div className="business-card__body">
                {group.rows.map((source) => (
                  <SourceRanking key={source.source_type} source={source}
                                 showComparison={Boolean(referenceLabel)} />
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
