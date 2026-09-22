import type {
  SatisfactionComparison, SatisfactionSourceComparison, SatisfactionSourceKpi,
  SatisfactionKpi,
} from "../api";
import { DASHBOARD_SOURCE_GROUPS } from "../dashboardSources";
import {
  CLIENT_STATUS_LABELS, formatCompactOnTen, formatPeriod, formatSatisfactionEvolution,
  satisfactionEvolution, SOURCE_LABELS, SOURCE_SHORT_LABELS,
} from "../satisfactionDisplay";
import { Badge, Card, InfoTip } from "../ui";

function DeltaBadge({ item }: { item?: SatisfactionSourceComparison }) {
  const outcome = satisfactionEvolution(
    item?.current_mean_on_10 ?? null, item?.reference_mean_on_10 ?? null, Boolean(item?.comparable),
  );
  if (outcome.kind !== "value") {
    return <Badge tone={outcome.kind === "new" ? "info" : "neutral"}>{formatSatisfactionEvolution(outcome)}</Badge>;
  }
  const tone = outcome.percent > 0 ? "success" : outcome.percent < 0 ? "danger" : "neutral";
  return <Badge tone={tone}>{formatSatisfactionEvolution(outcome)}</Badge>;
}

function ScoreGauge({ value }: { value: number | null }) {
  const percent = value == null ? 0 : Math.max(0, Math.min(100, value * 10));
  return (
    <div className="satisfaction-score">
      <div className="satisfaction-score__value">{formatCompactOnTen(value)}</div>
      <div className="satisfaction-score__track" aria-hidden="true">
        <span style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function SourceSummary({ source, compared }: {
  source: SatisfactionSourceKpi;
  compared?: SatisfactionSourceComparison;
}) {
  const segmentComparison = new Map(
    (compared?.by_client_status ?? []).map((item) => [item.client_status, item]),
  );
  const isMdtc = source.source_type.startsWith("MDTC-");
  const visibleSegments = isMdtc
    ? source.by_client_status
    : source.by_client_status.filter((segment) => (
      segment.client_status === "non_renseigne" && segment.respondent_count > 0
    ));

  return (
    <section className="satisfaction-source">
      <div className="satisfaction-source__heading">
        <div>
          <h4>{SOURCE_SHORT_LABELS[source.source_type] ?? source.source_type}</h4>
          <p>
            {formatPeriod(source.period.start, source.period.end)} · {source.respondent_count ?? "—"} répondant(s)
          </p>
        </div>
        {source.availability_status === "source_not_provided"
          ? <Badge tone="neutral">source non reçue</Badge>
          : compared ? <DeltaBadge item={compared} /> : null}
      </div>

      {!source.native_detail_available ? (
        <p className="business-notice">{source.availability_message}</p>
      ) : (
        <>
          <div className="satisfaction-source__scoreline">
            <ScoreGauge value={source.mean_on_10} />
            <div className="satisfaction-source__meta">
              <strong>{source.rated_respondent_count.toLocaleString("fr-FR")}</strong>
              <span>répondant(s) noté(s)</span>
              <small>
                {source.mean_native != null
                  ? `${source.mean_native.toFixed(2).replace(".", ",")} / ${source.native_scale_max} en natif`
                  : "aucune note exploitable"}
              </small>
            </div>
          </div>

          {visibleSegments.length > 0 && (
            <div className="satisfaction-segments">
              {visibleSegments.map((segment) => {
                const previous = segmentComparison.get(segment.client_status);
                return (
                  <div key={segment.client_status} className="satisfaction-segment">
                    <div>
                      <strong>{CLIENT_STATUS_LABELS[segment.client_status]}</strong>
                      <span>
                        {segment.respondent_count} répondant(s) · {segment.rated_respondent_count} noté(s)
                      </span>
                    </div>
                    <span className="satisfaction-segment__score">
                      {segment.respondent_count === 0
                        ? "aucune donnée"
                        : segment.rated_respondent_count === 0
                          ? "aucune note"
                          : formatCompactOnTen(segment.mean_on_10)}
                    </span>
                    {compared && (
                      <small>{formatSatisfactionEvolution(satisfactionEvolution(
                        previous?.current_mean_on_10 ?? null,
                        previous?.reference_mean_on_10 ?? null,
                        previous != null,
                      ))}</small>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <p className="satisfaction-source__footnote">
            {source.unrated_respondent_count ?? 0} sans note · {source.invalid_rating_count} note(s) invalide(s)
            {compared?.reference_rated_respondent_count != null
              ? ` · référence : ${compared.reference_rated_respondent_count} noté(s)` : ""}
          </p>
          {compared?.reason && <p className="ui-muted">Comparaison indisponible : {compared.reason}</p>}
          {compared?.warning && <p className="ui-field__error">{compared.warning}</p>}
          {source.availability_message && <p className="ui-muted">{source.availability_message}</p>}
        </>
      )}
    </section>
  );
}

/** Satisfaction déclarée : une réponse de questionnaire compte exactement une fois. */
export default function SatisfactionPanel({
  sat, titre = "Satisfaction client déclarée", comparison = null, referenceLabel = null,
}: {
  sat: SatisfactionKpi;
  titre?: string;
  comparison?: SatisfactionComparison | null;
  referenceLabel?: string | null;
}) {
  const comparisonBySource = new Map(
    (comparison?.by_source ?? []).map((item) => [item.source_type, item]),
  );
  const knownSources = new Set(DASHBOARD_SOURCE_GROUPS.flatMap((group) => group.sources));
  const historicalGroups = sat.by_source
    .filter((source) => !knownSources.has(source.source_type))
    .map((source) => ({
      key: `historical-${source.source_type}`,
      title: SOURCE_LABELS[source.source_type] ?? source.source_type,
      sources: [source.source_type],
    }));
  const groups = [...DASHBOARD_SOURCE_GROUPS, ...historicalGroups]
    .map((group) => ({
      ...group,
      rows: group.sources
        .map((source) => sat.by_source.find((item) => item.source_type === source))
        .filter((source): source is SatisfactionSourceKpi => source != null),
    }))
    .filter((group) => group.rows.length > 0);
  const missingSources = sat.by_source.filter(
    (source) => source.availability_status === "source_not_provided",
  );

  return (
    <section className="business-section" aria-labelledby="satisfaction-title">
      <div className="business-section__header">
        <div>
          <p className="business-section__eyebrow">Notes clients</p>
          <h2 id="satisfaction-title">{titre}</h2>
          <p className="ui-muted">
            Une voix par répondant, affichée sur 10 depuis l’échelle native.
            {referenceLabel ? ` Évolution comparée à ${referenceLabel}.` : ""}
          </p>
        </div>
        <InfoTip text="Chaque moyenne est calculée sur les répondants notés ayant produit au moins un verbatim analysé. La note native est divisée par le maximum de son échelle, puis multipliée par 10. « Statut client non disponible » signifie que la source ne permet pas de distinguer Ancien et Nouveau ; la note peut néanmoins être renseignée." />
      </div>

      {missingSources.length > 0 && (
        <p className="business-notice">
          Données non reçues dans ce lot : {missingSources
            .map((source) => SOURCE_LABELS[source.source_type] ?? source.source_type)
            .join(" · ")}.
        </p>
      )}

      {sat.historical_data_unavailable && (
        <p className="business-notice">
          Certains lots historiques ne conservent ni note native ni identifiant répondant :
          leur détail reste indisponible jusqu’à un retraitement explicite.
        </p>
      )}

      {groups.length === 0 ? (
        <Card><p className="ui-muted">Aucune réponse de questionnaire disponible sur ce périmètre.</p></Card>
      ) : (
        <div className="business-card-grid">
          {groups.map((group) => (
            <article key={group.key} className="business-card satisfaction-card">
              <header className="business-card__header">
                <h3>{group.title}</h3>
                <Badge tone="info">
                  {group.rows.reduce((total, source) => total + (source.respondent_count ?? 0), 0).toLocaleString("fr-FR")} répondant(s)
                </Badge>
              </header>
              <div className="business-card__body">
                {group.rows.map((source) => (
                  <SourceSummary key={source.source_type} source={source}
                                 compared={comparisonBySource.get(source.source_type)} />
                ))}
              </div>
            </article>
          ))}
        </div>
      )}

      {sat.global.mean_on_10 != null && (
        <p className="business-section__footnote">
          Indication secondaire multi-source : {formatCompactOnTen(sat.global.mean_on_10)} sur {sat.global.rated_respondent_count.toLocaleString("fr-FR")} répondant(s) noté(s).
          Chaque répondant est pondéré une seule fois. {sat.global.scope}
        </p>
      )}
    </section>
  );
}
