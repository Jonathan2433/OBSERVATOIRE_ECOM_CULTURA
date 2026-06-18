/** Graphe demandé : thème × sentiment × volumétrie (barres empilées par sentiment). */
const COLORS: Record<string, string> = {
  "Négatif": "#d64545",
  "Neutre": "#9aa0a6",
  "Positif": "#1a7f37",
};
const ORDER = ["Négatif", "Neutre", "Positif"];

export default function StackedSentimentBar({ data }: { data: Record<string, Record<string, number>> }) {
  const rows = Object.entries(data);
  if (rows.length === 0) return <p style={{ color: "#999" }}>Aucune donnée.</p>;
  const totalOf = (segs: Record<string, number>) => Object.values(segs).reduce((a, b) => a + b, 0);
  const maxTotal = Math.max(...rows.map(([, s]) => totalOf(s)), 1);

  return (
    <div>
      <div style={{ display: "flex", gap: "1rem", marginBottom: "0.5rem", fontSize: ".8rem" }}>
        {ORDER.map((s) => (
          <span key={s}><span style={{ display: "inline-block", width: 10, height: 10, background: COLORS[s], marginRight: 4 }} />{s}</span>
        ))}
      </div>
      <div style={{ display: "grid", gap: "0.35rem" }}>
        {rows.map(([theme, segs]) => {
          const total = totalOf(segs);
          return (
            <div key={theme} style={{ display: "grid", gridTemplateColumns: "minmax(140px, 240px) 1fr 48px", gap: "0.6rem", alignItems: "center" }}>
              <span style={{ fontSize: ".85rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={theme}>{theme}</span>
              <div style={{ display: "flex", height: 16, width: `${(total / maxTotal) * 100}%`, minWidth: 2, borderRadius: 4, overflow: "hidden" }}>
                {ORDER.map((s) => {
                  const v = segs[s] || 0;
                  if (!v) return null;
                  return <div key={s} title={`${s}: ${v}`} style={{ width: `${(v / total) * 100}%`, background: COLORS[s] }} />;
                })}
              </div>
              <span style={{ fontSize: ".85rem", textAlign: "right" }}>{total}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
