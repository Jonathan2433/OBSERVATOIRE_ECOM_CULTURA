/** Graphe thème × sentiment × volumétrie, avec sous-thèmes dépliables. */
import { useEffect, useId, useState } from "react";
import type {
  SentimentDistribution, ThemeSentimentDistribution, ThemeSentimentHierarchy,
} from "../api";
import { sortThemeSentimentRows, totalSentimentCount } from "../themeSentimentSort";

const COLORS: Record<string, string> = {
  "Négatif": "var(--cu-sentiment-negatif)",
  "Neutre": "var(--cu-sentiment-neutre)",
  "Positif": "var(--cu-sentiment-positif)",
};
const ORDER = ["Négatif", "Neutre", "Positif"];

function accessibleSummary(label: string, sentiments: SentimentDistribution) {
  const details = ORDER.map((sentiment) => `${sentiment.toLowerCase()} : ${sentiments[sentiment] ?? 0}`);
  return `${label} — ${totalSentimentCount(sentiments)} mention(s), ${details.join(", ")}`;
}

function SentimentRow({
  label,
  sentiments,
  maxTotal,
  child = false,
  expanded,
  controls,
  onToggle,
}: {
  label: string;
  sentiments: SentimentDistribution;
  maxTotal: number;
  child?: boolean;
  expanded?: boolean;
  controls?: string;
  onToggle?: () => void;
}) {
  const total = totalSentimentCount(sentiments);
  const content = (
    <>
      <span className="sentiment-bar__label" title={label}>
        {!child && (
          <span
            className={`sentiment-bar__chevron${onToggle ? "" : " is-placeholder"}`}
            aria-hidden="true"
          >
            {onToggle ? "›" : ""}
          </span>
        )}
        <span>{label}</span>
      </span>
      <span className="sentiment-bar__track" aria-hidden="true">
        <span
          className="sentiment-bar__stack"
          style={{ width: `${(total / maxTotal) * 100}%` }}
        >
          {ORDER.map((sentiment) => {
            const value = sentiments[sentiment] || 0;
            if (!value) return null;
            return (
              <span
                key={sentiment}
                title={`${sentiment}: ${value}`}
                style={{ width: `${(value / total) * 100}%`, background: COLORS[sentiment] }}
              />
            );
          })}
        </span>
      </span>
      <span className="sentiment-bar__value">{total}</span>
    </>
  );
  const className = [
    "sentiment-bar__row",
    child ? "sentiment-bar__row--child" : "sentiment-bar__row--parent",
    onToggle ? "sentiment-bar__row--selectable" : "",
    expanded ? "is-expanded" : "",
  ].filter(Boolean).join(" ");

  if (onToggle) {
    return (
      <button
        type="button"
        className={className}
        aria-expanded={expanded}
        aria-controls={controls}
        aria-label={`${accessibleSummary(label, sentiments)}. ${expanded ? "Replier" : "Déplier"} les sous-thèmes.`}
        onClick={onToggle}
      >
        {content}
      </button>
    );
  }
  return <div className={className} aria-label={accessibleSummary(label, sentiments)}>{content}</div>;
}

export default function StackedSentimentBar({
  data,
  hierarchy,
}: {
  data: ThemeSentimentDistribution;
  hierarchy?: ThemeSentimentHierarchy;
}) {
  const [expandedTheme, setExpandedTheme] = useState<string | null>(null);
  const componentId = useId();
  const rows = sortThemeSentimentRows(data);

  useEffect(() => {
    if (!expandedTheme) return;
    const children = hierarchy?.[expandedTheme];
    if (!(expandedTheme in data) || !children || Object.keys(children).length === 0) {
      setExpandedTheme(null);
    }
  }, [data, expandedTheme, hierarchy]);

  if (rows.length === 0) return <p className="ui-muted">Aucune donnée.</p>;
  const maxTotal = Math.max(...rows.map(([, s]) => totalSentimentCount(s)), 1);

  return (
    <div className="sentiment-bar">
      <div className="sentiment-bar__legend">
        {ORDER.map((s) => (
          <span key={s} className="ui-row" style={{ gap: 6 }}>
            <span className="sentiment-bar__legend-swatch" style={{ background: COLORS[s] }} />{s}
          </span>
        ))}
      </div>
      <p className="ui-muted sentiment-bar__description">
        Thèmes classés par nombre de verbatims négatifs décroissant.
        {hierarchy && " Sélectionnez un thème pour afficher ses sous-thèmes."}
      </p>
      <div className="sentiment-bar__rows">
        {rows.map(([theme, sentiments], index) => {
          const children = hierarchy?.[theme] ?? {};
          const hasChildren = Object.keys(children).length > 0;
          const expanded = expandedTheme === theme;
          const childrenId = `${componentId}-children-${index}`;
          return (
            <div key={theme} className="sentiment-bar__group">
              <SentimentRow
                label={theme}
                sentiments={sentiments}
                maxTotal={maxTotal}
                expanded={expanded}
                controls={hasChildren ? childrenId : undefined}
                onToggle={hasChildren
                  ? () => setExpandedTheme((current) => current === theme ? null : theme)
                  : undefined}
              />
              {expanded && (
                <div
                  id={childrenId}
                  className="sentiment-bar__children"
                  role="group"
                  aria-label={`Sous-thèmes de ${theme}`}
                >
                  {sortThemeSentimentRows(children).map(([subtheme, childSentiments]) => (
                    <SentimentRow
                      key={subtheme}
                      label={subtheme}
                      sentiments={childSentiments}
                      maxTotal={maxTotal}
                      child
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
