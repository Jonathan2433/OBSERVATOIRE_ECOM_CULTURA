/** Petit graphe en barres horizontales (sans dépendance, piloté par les tokens). */
export default function BarList({ data, color = "var(--cu-primary-500)" }: {
  data: Record<string, number>;
  color?: string;
  max?: number;
}) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return <p className="ui-muted">Aucune donnée.</p>;
  const top = Math.max(...entries.map(([, v]) => v), 1);
  return (
    <div style={{ display: "grid", gap: "var(--sp-2)" }}>
      {entries.map(([label, value]) => (
        <div key={label} style={{ display: "grid", gridTemplateColumns: "minmax(120px, 240px) 1fr 48px", gap: "var(--sp-3)", alignItems: "center" }}>
          <span style={{ fontSize: "var(--fs-sm)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={label}>{label}</span>
          <div style={{ background: "var(--cu-neutral-200)", borderRadius: "var(--r-pill)", height: 12 }}>
            <div style={{ width: `${(value / top) * 100}%`, background: color, height: "100%", borderRadius: "var(--r-pill)", transition: "width var(--t-base)" }} />
          </div>
          <span className="ui-table__num" style={{ fontSize: "var(--fs-sm)", textAlign: "right" }}>{value}</span>
        </div>
      ))}
    </div>
  );
}
