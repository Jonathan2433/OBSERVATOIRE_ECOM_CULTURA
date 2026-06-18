import { useEffect, useState, type FormEvent } from "react";
import {
  getMeta, getTaxonomy, predict,
  type AppMeta, type Prediction, type TaxonomyTheme,
} from "../api";
import { Badge, type BadgeTone, Button, Card, Textarea } from "../ui";

function sentimentTone(s?: string | null): BadgeTone {
  return s === "Négatif" ? "danger" : s === "Positif" ? "success" : "neutral";
}

const STEPS: { t: string; d: string }[] = [
  { t: "Dépôt des fichiers", d: "Vous chargez les exports Excel (MDTC, Mopinion). L'app vérifie les colonnes attendues." },
  { t: "Anonymisation (RGPD)", d: "Avant toute analyse, les données personnelles (e-mails, téléphones, n° de commande, noms) sont remplacées par des marqueurs [EMAIL], [TEL]… La base ne stocke jamais le texte brut." },
  { t: "Nettoyage", d: "Le texte est normalisé (ponctuation, casse) pour faciliter l'analyse. Les verbatims trop courts sont signalés." },
  { t: "Classification du thème", d: "Le modèle attribue 1 à 2 thèmes issus de la taxonomie (un grand thème « niv.1 » et un sous-thème « niv.2 » qui lui appartient)." },
  { t: "Sentiment", d: "Pour chaque thème, le modèle estime le ressenti : Négatif, Neutre ou Positif." },
  { t: "Signaux d'alerte", d: "Trois indicateurs binaires sont évalués : rupture client, churn (risque de départ), insatisfaction forte." },
  { t: "Confiance & routage", d: "Le modèle calcule un score de confiance (0 à 1). En dessous du seuil de revue, le verbatim est dirigé vers la revue humaine ; sinon il est classé « auto »." },
];

export default function AidePage() {
  const [meta, setMeta] = useState<AppMeta | null>(null);
  const [themes, setThemes] = useState<TaxonomyTheme[]>([]);
  const [text, setText] = useState("Le paiement a été refusé trois fois alors que ma carte fonctionne, je ne commanderai plus.");
  const [sat, setSat] = useState("2");
  const [res, setRes] = useState<Prediction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMeta().then(setMeta).catch(() => setMeta(null));
    getTaxonomy().then((t) => setThemes(t.themes)).catch(() => setThemes([]));
  }, []);

  const seuil = meta?.default_seuil_revue ?? 0.7;
  const nNiv2 = themes.reduce((acc, t) => acc + t.niv2.length, 0);

  const analyser = async (e: FormEvent) => {
    e.preventDefault();
    setError(null); setRes(null); setBusy(true);
    try {
      setRes(await predict(text.trim(), sat.trim() === "" ? null : Number(sat)));
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
        <h1 className="page-header__title">Comment ça marche</h1>
        <p className="page-header__sub">Comprendre ce que l'application fait de vos verbatims, étape par étape.</p>
      </div>

      <div className="ui-stack">
        <Card title="À quoi sert l'application">
          <p>
            L'Observatoire transforme des milliers de verbatims clients en <b>informations exploitables</b> :
            il identifie de quoi parle chaque retour (thème), le ressenti associé (sentiment) et d'éventuels
            <b> signaux d'alerte</b>. Les cas incertains sont mis de côté pour une <b>relecture humaine</b>.
            C'est un <b>outil d'aide à l'analyse</b> : chaque prédiction est accompagnée de son niveau de confiance.
          </p>
        </Card>

        <Card title="Le parcours d'un verbatim">
          <div className="ui-steps">
            {STEPS.map((s, i) => (
              <div className="ui-step" key={i}>
                <div className="ui-step__num">{i + 1}</div>
                <div>
                  <div className="ui-step__title">{s.t}</div>
                  <div className="ui-step__desc">
                    {s.d}
                    {i === 3 && themes.length > 0 && <> <em>(actuellement {themes.length} grands thèmes, {nNiv2} sous-thèmes)</em>.</>}
                    {i === 6 && <> <em>(seuil de revue par défaut : {seuil.toFixed(2)})</em>.</>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Essayer sur un exemple">
          <p className="ui-muted">Saisissez un verbatim : vous verrez le résultat tel que l'app le produirait (rien n'est enregistré).</p>
          <form onSubmit={analyser} className="ui-stack" style={{ maxWidth: 640, marginTop: "var(--sp-3)" }}>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} required />
            <div className="ui-row">
              <label className="ui-field" style={{ maxWidth: 200 }}>
                <span className="ui-field__label">Note de satisfaction (1–10, option.)</span>
                <input className="ui-input" type="number" min={1} max={10} value={sat} onChange={(e) => setSat(e.target.value)} />
              </label>
              <Button type="submit" variant="primary" loading={busy} disabled={!text.trim()} style={{ alignSelf: "flex-end" }}>Analyser</Button>
            </div>
          </form>
          {error && <p className="ui-field__error">{error}</p>}
          {res && (
            <div className="ui-verbatim" style={{ marginTop: "var(--sp-4)" }}>
              <dl className="ui-dl">
                <dt>Texte anonymisé</dt><dd>{res["verbatim_analysé"]}</dd>
                <dt>Thème</dt><dd>{res.theme1_niv1} / {res.theme1_niv2} <Badge tone={sentimentTone(res.theme1_sentiment)}>{res.theme1_sentiment}</Badge></dd>
                <dt>Signaux</dt><dd>{signals.length ? <span className="ui-row" style={{ gap: 4 }}>{signals.map((s) => <Badge key={s} tone="warning">{s}</Badge>)}</span> : <span className="ui-muted">aucun</span>}</dd>
                <dt>Confiance</dt><dd>{String(res.confidence_globale)} {Number(res.confidence_globale) < seuil ? <Badge tone="warning" dot>sous le seuil ({seuil.toFixed(2)})</Badge> : <Badge tone="success" dot>au-dessus du seuil</Badge>}</dd>
                <dt>Routage</dt><dd>{res.revue_humaine_requise ? "→ en revue humaine" : "→ classé automatiquement"}</dd>
              </dl>
            </div>
          )}
        </Card>

        <Card title="Les notions clés">
          <dl className="ui-dl">
            <dt>Thème niv.1 / niv.2</dt><dd>Le grand thème (ex. « Tunnel de vente - Paiement ») et son sous-thème (ex. « Bug paiement »). Un sous-thème appartient toujours à un seul grand thème.</dd>
            <dt>Sentiment</dt><dd>Le ressenti exprimé : <Badge tone="danger">Négatif</Badge> <Badge tone="neutral">Neutre</Badge> <Badge tone="success">Positif</Badge>.</dd>
            <dt>Signaux</dt><dd><Badge tone="danger">rupture client</Badge> (rupture de la relation), <Badge tone="warning">churn</Badge> (risque de départ), <Badge tone="warning">insatisfaction forte</Badge>.</dd>
            <dt>Confiance</dt><dd>De 0 à 1, le degré de certitude du modèle. Plus c'est bas, plus une relecture est utile.</dd>
            <dt>Seuil de revue</dt><dd>La limite (défaut {seuil.toFixed(2)}, réglable par lot) en dessous de laquelle un verbatim part en revue humaine.</dd>
            <dt>Statut</dt><dd><Badge tone="success" dot>auto</Badge> (classé sans relecture), <Badge tone="warning" dot>en revue</Badge> (à vérifier), <Badge tone="primary">corrigé</Badge> (revu par un humain).</dd>
          </dl>
        </Card>

        <Card title="Lire les résultats et les tableaux de bord">
          <ul style={{ lineHeight: 1.7, paddingLeft: "1.2rem" }}>
            <li><b>Taux de revue</b> = part des verbatims dont la confiance est sous le seuil (à relire).</li>
            <li><b>Distributions</b> (thèmes, sentiments) = simples comptages sur le lot.</li>
            <li><b>Thèmes × sentiment</b> = pour chaque thème, la répartition Négatif / Neutre / Positif et le volume.</li>
            <li><b>KPI modèle</b> = qualité mesurée à l'entraînement ; une alerte s'affiche si un indicateur passe sous sa cible.</li>
          </ul>
        </Card>

        <Card title="Confidentialité & limites">
          <ul style={{ lineHeight: 1.7, paddingLeft: "1.2rem" }}>
            <li>🔒 Les données personnelles sont <b>anonymisées avant tout traitement</b> ; la base ne contient que du texte anonymisé.</li>
            <li>Tout reste <b>sur ce poste</b> : aucune donnée n'est envoyée à l'extérieur.</li>
            <li>Une prédiction est une <b>aide</b>, pas une vérité : score de confiance et statut sont toujours affichés.</li>
            <li>L'app ne déclenche <b>aucune action</b> vers les clients.</li>
          </ul>
          <p className="ui-muted" style={{ marginTop: "var(--sp-3)" }}>
            Modèle actif : <b>{meta?.active_model ? `${meta.active_model.label} (${meta.active_model.kind})` : "—"}</b>
            {meta?.active_model?.kind === "stub" && " — modèle de démonstration en attendant le modèle entraîné."}
          </p>
        </Card>
      </div>
    </div>
  );
}
