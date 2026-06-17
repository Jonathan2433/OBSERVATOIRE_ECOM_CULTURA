import { useState, type FormEvent } from "react";
import { predict, type Prediction } from "../api";

export default function TestPage() {
  const [text, setText] = useState("");
  const [sat, setSat] = useState<string>("");
  const [res, setRes] = useState<Prediction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setRes(null);
    setBusy(true);
    try {
      const satNum = sat.trim() === "" ? null : Number(sat);
      setRes(await predict(text.trim(), satNum));
    } catch (err: any) {
      setError(err?.message ?? "Erreur");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1>Test à la volée</h1>
      <p style={{ color: "#666" }}>Classez un verbatim isolé avec le modèle actif (diagnostic / démonstration).</p>

      <form onSubmit={onSubmit} style={{ display: "grid", gap: "0.75rem", maxWidth: 640 }}>
        <textarea value={text} onChange={(e) => setText(e.target.value)} required rows={4}
                  placeholder="Saisissez un verbatim client…" />
        <label>Note de satisfaction (1–10, optionnel)
          <input type="number" min={1} max={10} value={sat} onChange={(e) => setSat(e.target.value)} style={{ marginLeft: 8, width: 70 }} />
        </label>
        <div><button type="submit" disabled={busy || !text.trim()}>{busy ? "Analyse…" : "Analyser"}</button></div>
      </form>

      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {res && (
        <section style={{ marginTop: "1.5rem", padding: "1rem 1.25rem", border: "1px solid #eee", borderRadius: 8, maxWidth: 640 }}>
          <h3 style={{ marginTop: 0 }}>
            Résultat {res.revue_humaine_requise ? "⚠️ (revue conseillée)" : "✓"}
            <span style={{ float: "right", color: "#999", fontSize: ".8rem" }}>{res.model_label}</span>
          </h3>
          <ul style={{ lineHeight: 1.7 }}>
            <li><b>Thème 1</b> : {res.theme1_niv1 || "—"} / {res.theme1_niv2 || "—"} ({res.theme1_sentiment}) — conf. {String(res.theme1_score_confiance)}</li>
            {res.nb_themes === 2 && <li><b>Thème 2</b> : {res.theme2_niv1} / {res.theme2_niv2} ({res.theme2_sentiment})</li>}
            <li><b>Signaux</b> : {[res.signal_rupture_client && "rupture client", res.signal_churn && "churn", res.signal_insatisfaction_forte && "insatisfaction forte"].filter(Boolean).join(", ") || "aucun"}</li>
            <li><b>Confiance globale</b> : {String(res.confidence_globale)}</li>
            <li style={{ color: "#888" }}><b>Texte analysé</b> : {res["verbatim_analysé"]}</li>
          </ul>
        </section>
      )}
    </div>
  );
}
