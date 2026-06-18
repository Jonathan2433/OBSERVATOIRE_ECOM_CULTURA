import { useEffect, useState } from "react";
import { getModelKpi, getVolumetry, type ModelKpi, type Volumetry } from "../api";
import BarList from "../components/BarList";
import StackedSentimentBar from "../components/StackedSentimentBar";

const METRIC_LABELS: Record<string, string> = {
  f1_macro_niv1: "F1-macro niv.1",
  f1_macro_niv2: "F1-macro niv.2",
  accuracy_sentiment: "Accuracy sentiment",
  recall_rupture: "Rappel rupture",
};

export default function DashboardsPage() {
  const [model, setModel] = useState<ModelKpi | null>(null);
  const [vol, setVol] = useState<Volumetry | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getModelKpi().then(setModel).catch((e) => setError(String(e.message ?? e)));
    getVolumetry().then(setVol).catch((e) => setError(String(e.message ?? e)));
  }, []);

  return (
    <div>
      <h1>Tableaux de bord</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <section style={{ marginBottom: "2rem", padding: "1rem 1.25rem", border: "1px solid #eee", borderRadius: 8 }}>
        <h3 style={{ marginTop: 0 }}>Modèle actif</h3>
        {!model && <p>Chargement…</p>}
        {model && model.active === null && <p style={{ color: "#999" }}>Aucun modèle actif.</p>}
        {model && model.active && (
          <>
            <p><b>{model.active.label}</b> ({model.active.kind})</p>
            {model.active.kind === "stub" && (
              <p style={{ color: "#a06000" }}>
                Modèle de démonstration (heuristique) — pas de métriques d'évaluation.
                Entraînez et déposez un modèle CamemBERT pour obtenir les KPI qualité.
              </p>
            )}
            {model.active.metrics && Object.keys(model.active.metrics).length > 0 && (
              <ul>
                {Object.entries(model.active.metrics).map(([k, v]) => (
                  <li key={k}>{METRIC_LABELS[k] ?? k} : <b>{typeof v === "number" ? v.toFixed(3) : String(v)}</b></li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      <section>
        <h3>Volumétrie</h3>
        {!vol && <p>Chargement…</p>}
        {vol && (
          <>
            <p style={{ color: "#666" }}>{vol.n_batches} lot(s) traité(s) · {vol.total_verbatims} verbatims au total</p>

            <h4>Répartition globale des thèmes</h4>
            <BarList data={vol.global_themes} />

            <h4 style={{ marginTop: "2rem" }}>Thèmes × sentiment (volumétrie globale)</h4>
            <StackedSentimentBar data={vol.theme_sentiment} />

            <h4 style={{ marginTop: "2rem" }}>Évolution par lot</h4>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: ".9rem" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "2px solid #ddd" }}>
                  <th style={{ padding: "0.3rem" }}>Lot</th><th>Verbatims</th><th>Taux revue</th>
                  <th>Rupture</th><th>Churn</th><th>Insatisf.</th>
                </tr>
              </thead>
              <tbody>
                {vol.series.map((s) => (
                  <tr key={s.id} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: "0.3rem" }}>{s.label}</td>
                    <td>{s.n_total}</td>
                    <td>{(s.review_rate * 100).toFixed(1)}%</td>
                    <td>{s.signals.rupture}</td>
                    <td>{s.signals.churn}</td>
                    <td>{s.signals.insatisfaction}</td>
                  </tr>
                ))}
                {vol.series.length === 0 && <tr><td colSpan={6} style={{ color: "#888", padding: "0.5rem" }}>Aucun lot terminé.</td></tr>}
              </tbody>
            </table>
          </>
        )}
      </section>
    </div>
  );
}
