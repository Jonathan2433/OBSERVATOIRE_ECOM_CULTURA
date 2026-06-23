import { useEffect, useState, type FormEvent } from "react";
import { listModels, predict, type ModelVersion, type Prediction } from "../api";
import { Badge, type BadgeTone, Button, Card, Input, Select, Textarea } from "../ui";

function sentimentTone(s?: string | null): BadgeTone {
  return s === "Négatif" ? "danger" : s === "Positif" ? "success" : "neutral";
}

const KIND_LABEL: Record<string, string> = {
  real: "CamemBERT", lmstudio: "LM Studio", stub: "Démo", claude: "Claude",
};

/** Libellé d'une option du sélecteur de moteur (marque Claude « comparaison »). */
function engineOptionLabel(m: ModelVersion): string {
  const kind = KIND_LABEL[m.kind] ?? m.kind;
  const tag = m.kind === "claude" ? " · comparaison" : m.is_active ? " · actif" : "";
  return `${m.label} (${kind})${tag}`;
}

export default function TestPage() {
  const [text, setText] = useState("");
  const [sat, setSat] = useState("");
  const [modelId, setModelId] = useState("");          // "" = modèle actif (auto)
  const [models, setModels] = useState<ModelVersion[]>([]);
  const [res, setRes] = useState<Prediction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listModels().then((m) => setModels(m.filter((x) => x.available))).catch(() => setModels([]));
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null); setRes(null); setBusy(true);
    try {
      const satNum = sat.trim() === "" ? null : Number(sat);
      const mid = modelId === "" ? null : Number(modelId);
      setRes(await predict(text.trim(), satNum, mid));
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
        <p className="page-header__sub">Classez un verbatim isolé avec le moteur de votre choix (diagnostic / comparaison). Rien n'est enregistré.</p>
      </div>

      <div className="ui-stack" style={{ maxWidth: 680 }}>
        <Card title="Verbatim à analyser">
          <form onSubmit={onSubmit} className="ui-stack">
            <Textarea value={text} onChange={(e) => setText(e.target.value)} required rows={4}
                      placeholder="Saisissez un verbatim client…" />
            <div className="ui-row ui-row--wrap" style={{ gap: "var(--sp-3)", alignItems: "flex-end" }}>
              <Input label="Note de satisfaction (1–10, optionnel)" type="number" min={1} max={10}
                     value={sat} onChange={(e) => setSat(e.target.value)} style={{ maxWidth: 120 }} />
              <Select label="Moteur" value={modelId} onChange={(e) => setModelId(e.target.value)}
                      hint="« Claude » est un moteur de comparaison (non utilisable en production)."
                      style={{ maxWidth: 320 }}>
                <option value="">Modèle actif (par défaut)</option>
                {models.map((m) => (
                  <option key={m.id} value={String(m.id)}>{engineOptionLabel(m)}</option>
                ))}
              </Select>
            </div>
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
