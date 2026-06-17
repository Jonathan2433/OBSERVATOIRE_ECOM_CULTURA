import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { exportUrl, listResults, type ResultFilters, type ResultsResponse } from "../api";

const PAGE = 50;

export default function ResultsPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [data, setData] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<ResultFilters>({});

  useEffect(() => {
    listResults(batchId, { ...filters, limit: PAGE, offset })
      .then(setData)
      .catch((e) => setError(String(e.message ?? e)));
  }, [batchId, offset, filters]);

  const apply = (patch: ResultFilters) => { setOffset(0); setFilters((f) => ({ ...f, ...patch })); };

  return (
    <div>
      <p><Link to={`/lots/${batchId}`}>← Lot #{batchId}</Link></p>
      <h1>Résultats du lot #{batchId}</h1>

      <div style={{ display: "flex", gap: "1rem", marginBottom: "1rem" }}>
        <a href={exportUrl(batchId, "csv")}><button>Export CSV</button></a>
        <a href={exportUrl(batchId, "xlsx")}><button>Export Excel</button></a>
      </div>

      <section style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "center", marginBottom: "1rem" }}>
        <input placeholder="Recherche texte…" onChange={(e) => apply({ q: e.target.value || undefined })} />
        <input placeholder="Thème niv.1" onChange={(e) => apply({ niv1: e.target.value || undefined })} />
        <select onChange={(e) => apply({ sentiment: e.target.value || undefined })}>
          <option value="">Sentiment (tous)</option>
          <option>Négatif</option><option>Neutre</option><option>Positif</option>
        </select>
        <label><input type="checkbox" onChange={(e) => apply({ revue: e.target.checked ? true : undefined })} /> en revue</label>
        <label><input type="checkbox" onChange={(e) => apply({ rupture: e.target.checked || undefined })} /> rupture</label>
        <label><input type="checkbox" onChange={(e) => apply({ churn: e.target.checked || undefined })} /> churn</label>
        <label><input type="checkbox" onChange={(e) => apply({ insatisfaction: e.target.checked || undefined })} /> insatisf.</label>
      </section>

      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {data && (
        <>
          <p style={{ color: "#666" }}>{data.total} résultat(s) — affichage {data.total ? offset + 1 : 0}–{offset + data.items.length}</p>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: ".9rem" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #ddd" }}>
                <th style={{ padding: "0.3rem" }}>Verbatim (anonymisé)</th>
                <th>Thème 1</th><th>Sentiment</th><th>Signaux</th><th>Conf.</th><th>Revue</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.3rem", maxWidth: 360 }}>{r.verbatim_analyse.slice(0, 120)}</td>
                  <td>{r.theme1_niv1 ? `${r.theme1_niv1} / ${r.theme1_niv2}` : "—"}</td>
                  <td>{r.theme1_sentiment ?? "—"}</td>
                  <td>{[r.signal_rupture && "rupture", r.signal_churn && "churn", r.signal_insatisfaction && "insatisf."].filter(Boolean).join(", ") || "—"}</td>
                  <td>{r.confidence_globale != null ? r.confidence_globale.toFixed(2) : "—"}</td>
                  <td>{r.revue_requise ? "⚠️" : "✓"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ display: "flex", gap: "1rem", marginTop: "1rem", alignItems: "center" }}>
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>← Précédent</button>
            <button disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Suivant →</button>
          </div>
        </>
      )}
    </div>
  );
}
