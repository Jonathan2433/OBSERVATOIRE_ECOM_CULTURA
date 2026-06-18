/** Graphe thème × sentiment × volumétrie (barres empilées par sentiment), tokens. */
const COLORS: Record<string, string> = {
  "Négatif": "var(--cu-sentiment-negatif)",
  "Neutre": "var(--cu-sentiment-neutre)",
  "Positif": "var(--cu-sentiment-positif)",
};
const ORDER = ["Négatif", "Neutre", "Positif"];

export default function StackedSentimentBar({ data }: { data: Record<string, Record<string, number>> }) {
  const totalOf = (segs: Record<string, number>) => Object.values(segs).reduce((a, b) => a + b, 0);
  const rows = Object.entries(data).sort((a, b) => totalOf(b[1]) - totalOf(a[1]));
  if (rows.length === 0) return <p className="ui-muted">Aucune donnée.</p>;
  const maxTotal = Math.max(...rows.map(([, s]) => totalOf(s)), 1);

  return (
    <div>
      <div style={{ display: "flex", gap: "var(--sp-4)", marginBottom: "var(--sp-3)", fontSize: "var(--fs-xs)" }}>
        {ORDER.map((s) => (
          <span key={s} className="ui-row" style={{ gap: 6 }}>
            <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 2, background: COLORS[s] }} />{s}
          </span>
        ))}
      </div>
      <div style={{ display: "grid", gap: "var(--sp-2)" }}>
        {rows.map(([theme, segs]) => {
          const total = totalOf(segs);
          return (
            <div key={theme} style={{ display: "grid", gridTemplateColumns: "minmax(140px, 240px) 1fr 48px", gap: "var(--sp-3)", alignItems: "center" }}>
              <span style={{ fontSize: "var(--fs-sm)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={theme}>{theme}</span>
              <div style={{ display: "flex", height: 14, width: `${(total / maxTotal) * 100}%`, minWidth: 2, borderRadius: "var(--r-pill)", overflow: "hidden" }}>
                {ORDER.map((s) => {
                  const v = segs[s] || 0;
                  if (!v) return null;
                  return <div key={s} title={`${s}: ${v}`} style={{ width: `${(v / total) * 100}%`, background: COLORS[s] }} />;
                })}
              </div>
              <span className="ui-table__num" style={{ fontSize: "var(--fs-sm)", textAlign: "right" }}>{total}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
