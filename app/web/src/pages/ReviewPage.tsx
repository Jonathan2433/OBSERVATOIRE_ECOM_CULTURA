import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  correctResult, exportCorrectionsUrl, getReviewQueue, getTaxonomy,
  type ResultRow, type TaxonomyTheme,
} from "../api";

const SENTIMENTS = ["Négatif", "Neutre", "Positif"];

export default function ReviewPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [themes, setThemes] = useState<TaxonomyTheme[]>([]);
  const [item, setItem] = useState<ResultRow | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Champs de correction
  const [niv1, setNiv1] = useState("");
  const [niv2, setNiv2] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [sigR, setSigR] = useState(false);
  const [sigC, setSigC] = useState(false);
  const [sigI, setSigI] = useState(false);

  const loadNext = () => {
    getReviewQueue(batchId, 0, 1)
      .then((r) => {
        setRemaining(r.total);
        const it = r.items[0] ?? null;
        setItem(it);
        if (it) {
          setNiv1(it.theme1_niv1 ?? "");
          setNiv2(it.theme1_niv2 ?? "");
          setSentiment(it.theme1_sentiment ?? "");
          setSigR(it.signal_rupture); setSigC(it.signal_churn); setSigI(it.signal_insatisfaction);
        }
      })
      .catch((e) => setError(String(e.message ?? e)));
  };

  useEffect(() => {
    getTaxonomy().then((t) => setThemes(t.themes)).catch(() => setThemes([]));
    loadNext();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const childrenOf = (n1: string) => themes.find((t) => t.niv1 === n1)?.niv2 ?? [];

  const onNiv1Change = (v: string) => {
    setNiv1(v);
    const kids = childrenOf(v);
    if (!kids.includes(niv2)) setNiv2(kids[0] ?? "");
  };

  const submit = async (action: "validate" | "correct") => {
    if (!item) return;
    setBusy(true);
    setError(null);
    try {
      await correctResult(item.id, action === "validate" ? { action } : {
        action, theme1_niv1: niv1, theme1_niv2: niv2, theme1_sentiment: sentiment,
        signal_rupture: sigR, signal_churn: sigC, signal_insatisfaction: sigI,
      });
      loadNext();
    } catch (e: any) {
      setError(e?.message ?? "Erreur");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <p><Link to={`/lots/${batchId}`}>← Lot #{batchId}</Link></p>
      <h1>Revue humaine — lot #{batchId}</h1>
      <p style={{ color: "#666" }}>
        {remaining} verbatim(s) à revoir · <a href={exportCorrectionsUrl()}>exporter les corrections validées</a>
      </p>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {!item && <p style={{ fontSize: "1.1rem" }}>✅ File de revue vide — rien à revoir.</p>}

      {item && (
        <section style={{ padding: "1.25rem", border: "1px solid #ddd", borderRadius: 8, maxWidth: 680 }}>
          <p style={{ fontStyle: "italic", background: "#fafafa", padding: "0.75rem", borderRadius: 6 }}>
            « {item.verbatim_analyse} »
          </p>
          <p style={{ color: "#888", fontSize: ".85rem" }}>
            Proposition modèle : {item.theme1_niv1} / {item.theme1_niv2} · {item.theme1_sentiment} ·
            confiance {item.confidence_globale?.toFixed(2)}
          </p>

          <div style={{ display: "grid", gap: "0.6rem", marginTop: "1rem" }}>
            <label>Thème niv.1
              <select value={niv1} onChange={(e) => onNiv1Change(e.target.value)} style={{ marginLeft: 8 }}>
                {themes.map((t) => <option key={t.niv1}>{t.niv1}</option>)}
              </select>
            </label>
            <label>Sous-thème niv.2
              <select value={niv2} onChange={(e) => setNiv2(e.target.value)} style={{ marginLeft: 8 }}>
                {childrenOf(niv1).map((n) => <option key={n}>{n}</option>)}
              </select>
            </label>
            <label>Sentiment
              <select value={sentiment} onChange={(e) => setSentiment(e.target.value)} style={{ marginLeft: 8 }}>
                {SENTIMENTS.map((s) => <option key={s}>{s}</option>)}
              </select>
            </label>
            <div style={{ display: "flex", gap: "1rem" }}>
              <label><input type="checkbox" checked={sigR} onChange={(e) => setSigR(e.target.checked)} /> rupture client</label>
              <label><input type="checkbox" checked={sigC} onChange={(e) => setSigC(e.target.checked)} /> churn</label>
              <label><input type="checkbox" checked={sigI} onChange={(e) => setSigI(e.target.checked)} /> insatisfaction</label>
            </div>
          </div>

          <div style={{ display: "flex", gap: "1rem", marginTop: "1.25rem" }}>
            <button disabled={busy} onClick={() => submit("validate")}>Valider tel quel</button>
            <button disabled={busy} onClick={() => submit("correct")} style={{ fontWeight: 600 }}>Corriger &amp; valider</button>
          </div>
        </section>
      )}
    </div>
  );
}
