import { useState, type FormEvent } from "react";
import { predict, type Prediction } from "../api";
import { Badge, type BadgeTone, Button, Card, Input, Textarea } from "../ui";

function sentimentTone(s?: string | null): BadgeTone {
  return s === "Négatif" ? "danger" : s === "Positif" ? "success" : "neutral";
}

export default function TestPage() {
  const [text, setText] = useState("");
  const [sat, setSat] = useState("");
  const [res, setRes] = useState<Prediction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null); setRes(null); setBusy(true);
    try {
      const satNum = sat.trim() === "" ? null : Number(sat);
      setRes(await predict(text.trim(), satNum));
    } catch (err: any) {
      setError(err?.message ?? "Erreur");
    } finally {
      setBusy(false);
    }
  };

  const signals = res ? [
    res.signal_rupture_client && "rupture client",
    res.signal_churn && "churn",
    res.signal_insatisfaction_forte && "insatisfaction forte",
  ].filter(Boolean) as string[] : [];

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Test à la volée</h1>
        <p className="page-header__sub">Classez un verbatim isolé avec le modèle actif (diagnostic / démonstration). Rien n'est enregistré.</p>
      </div>

      <div className="ui-stack" style={{ maxWidth: 680 }}>
        <Card title="Verbatim à analyser">
          <form onSubmit={onSubmit} className="ui-stack">
            <Textarea value={text} onChange={(e) => setText(e.target.value)} required rows={4}
                      placeholder="Saisissez un verbatim client…" />
            <Input label="Note de satisfaction (1–10, optionnel)" type="number" min={1} max={10}
                   value={sat} onChange={(e) => setSat(e.target.value)} style={{ maxWidth: 120 }} />
            <div>
              <Button type="submit" variant="primary" loading={busy} disabled={!text.trim()}>
                {busy ? "Analyse…" : "Analyser"}
              </Button>
            </div>
          </form>
        </Card>

        {error && <p className="ui-field__error">{error}</p>}

        {res && (
          <Card
            title="Résultat"
            actions={<span className="ui-row">
              {res.revue_humaine_requise ? <Badge tone="warning" dot>revue conseillée</Badge> : <Badge tone="success" dot>auto</Badge>}
              {res.model_label && <Badge tone="neutral">{res.model_label}</Badge>}
            </span>}
          >
            <dl className="ui-dl">
              <dt>Thème 1</dt>
              <dd className="ui-row ui-row--wrap">
                {res.theme1_niv1 || "—"} / {res.theme1_niv2 || "—"}
                <Badge tone={sentimentTone(res.theme1_sentiment)}>{res.theme1_sentiment}</Badge>
                <span className="ui-muted">conf. {String(res.theme1_score_confiance)}</span>
              </dd>
              {res.nb_themes === 2 && (
                <>
                  <dt>Thème 2</dt>
                  <dd>{res.theme2_niv1} / {res.theme2_niv2} <Badge tone={sentimentTone(res.theme2_sentiment)}>{res.theme2_sentiment}</Badge></dd>
                </>
              )}
              <dt>Signaux</dt>
              <dd>{signals.length
                ? <span className="ui-row" style={{ gap: 4 }}>{signals.map((s) => <Badge key={s} tone="warning">{s}</Badge>)}</span>
                : <span className="ui-muted">aucun</span>}</dd>
              <dt>Confiance globale</dt><dd>{String(res.confidence_globale)}</dd>
              <dt>Texte analysé</dt><dd className="ui-muted">{res["verbatim_analysé"]}</dd>
            </dl>
          </Card>
        )}
      </div>
    </div>
  );
}
