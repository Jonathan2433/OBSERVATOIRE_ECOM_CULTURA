/** Petit graphe en barres horizontales (sans dépendance). */
export default function BarList({ data, color = "#0b5cad", max }: {
  data: Record<string, number>;
  color?: string;
  max?: number;
}) {
  const entries = Object.entries(data);
  if (entries.length === 0) return <p style={{ color: "#999" }}>Aucune donnée.</p>;
  const top = max ? Math.max(...entries.map(([, v]) => v), 1) : Math.max(...entries.map(([, v]) => v), 1);
  return (
    <div style={{ display: "grid", gap: "0.35rem" }}>
      {entries.map(([label, value]) => (
        <div key={label} style={{ display: "grid", gridTemplateColumns: "minmax(120px, 220px) 1fr 48px", gap: "0.6rem", alignItems: "center" }}>
          <span style={{ fontSize: ".85rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={label}>{label}</span>
          <div style={{ background: "#eee", borderRadius: 4, height: 14 }}>
            <div style={{ width: `${(value / top) * 100}%`, background: color, height: "100%", borderRadius: 4 }} />
          </div>
          <span style={{ fontSize: ".85rem", textAlign: "right" }}>{value}</span>
        </div>
      ))}
    </div>
  );
}
