import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  correctResult, exportCorrectionsUrl, getReviewQueue, getTaxonomy,
  type ResultRow, type TaxonomyTheme,
} from "../api";
import { Badge, Button, Card, Chip, EmptyState, Input, ProgressBar, Select, Spinner } from "../ui";

const SENTIMENTS = ["Négatif", "Neutre", "Positif"];

export default function ReviewPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [themes, setThemes] = useState<TaxonomyTheme[]>([]);
  const [item, setItem] = useState<ResultRow | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const initialTotal = useRef(0);

  const [niv1, setNiv1] = useState("");
  const [niv2, setNiv2] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [sigR, setSigR] = useState(false);
  const [sigC, setSigC] = useState(false);
  const [sigI, setSigI] = useState(false);

  const loadNext = () => {
    getReviewQueue(batchId, 0, 1)
      .then((r) => {
        setLoaded(true);
        setRemaining(r.total);
        if (initialTotal.current === 0 && r.total > 0) initialTotal.current = r.total;
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

  const norm = (s: string) => s.trim().toLowerCase();
  // Sous-thèmes suggérés pour un thème existant (comparaison insensible à la casse
  // pour rester cohérent avec la normalisation côté API). Vide si le thème est nouveau.
  const childrenOf = (n1: string) =>
    themes.find((t) => norm(t.niv1) === norm(n1))?.niv2 ?? [];
  // Un sous-thème « connu du référentiel » (de n'importe quel thème) vs. saisi librement.
  const isKnownSubtheme = (n2: string) =>
    !!norm(n2) && themes.some((t) => t.niv2.some((c) => norm(c) === norm(n2)));

  // Réalignement du sous-thème déclenché à la SORTIE du champ thème (événement
  // « commit »), jamais à chaque frappe : on ne repositionne que si le sous-thème
  // courant est un reliquat du référentiel (vide, ou sous-thème d'un AUTRE thème),
  // jamais un sous-thème que le relecteur vient de saisir librement.
  const realignNiv2OnBlur = () => {
    const kids = childrenOf(niv1);
    if (kids.length && !kids.includes(niv2) && (niv2 === "" || isKnownSubtheme(niv2))) {
      setNiv2(kids[0]);
    }
  };

  const submit = async (action: "validate" | "correct") => {
    if (!item || busy) return;
    setBusy(true);
    setError(null);
    try {
      await correctResult(item.id, action === "validate" ? { action } : {
        action, theme1_niv1: niv1, theme1_niv2: niv2, theme1_sentiment: sentiment,
        signal_rupture: sigR, signal_churn: sigC, signal_insatisfaction: sigI,
      });
      // Une correction a pu introduire un nouveau thème/sous-thème : on rafraîchit
      // le référentiel pour qu'il soit proposé sur les verbatims suivants.
      if (action === "correct") {
        getTaxonomy().then((t) => setThemes(t.themes)).catch(() => { /* garde l'ancien */ });
      }
      loadNext();
    } catch (e: any) {
      setError(e?.message ?? "Erreur");
    } finally {
      setBusy(false);
    }
  };

  // Raccourcis clavier (ignorés quand on est dans un champ).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === "v" || e.key === "V") { e.preventDefault(); submit("validate"); }
      if (e.key === "c" || e.key === "C") { e.preventDefault(); submit("correct"); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item, busy, niv1, niv2, sentiment, sigR, sigC, sigI]);

  const done = Math.max(0, initialTotal.current - remaining);
  const pct = initialTotal.current ? Math.round((done / initialTotal.current) * 100) : 0;

  return (
    <div>
      {error && <p className="ui-field__error">{error}</p>}
      {!loaded && <Spinner label="Chargement de la file…" />}

      {loaded && (
        <div className="ui-stack" style={{ maxWidth: 720 }}>
          <Card>
            <div className="ui-row">
              <ProgressBar value={pct} />
              <span className="ui-muted" style={{ whiteSpace: "nowrap" }}>{remaining} à revoir</span>
              <div className="ui-spacer" />
              <a className="ui-btn ui-btn--ghost ui-btn--sm" href={exportCorrectionsUrl()}>Exporter les corrections</a>
            </div>
          </Card>

          {!item ? (
            <EmptyState title="File de revue vide ✓" description="Tous les verbatims incertains de ce lot ont été traités." />
          ) : (
            <Card title={`Verbatim #${item.row_index}`}>
              <div className="ui-stack">
                <div className="ui-verbatim" style={{ fontStyle: "italic" }}>« {item.verbatim_analyse} »</div>
                <div className="ui-row ui-row--wrap" style={{ fontSize: "var(--fs-sm)" }}>
                  <span className="ui-muted">Proposition modèle :</span>
                  <Badge tone="neutral">{item.theme1_niv1} / {item.theme1_niv2}</Badge>
                  <Badge tone="neutral">{item.theme1_sentiment}</Badge>
                  <span className="ui-muted">confiance {item.confidence_globale?.toFixed(2)}</span>
                </div>

                <div className="ui-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                  <Input
                    label="Thème niv.1"
                    list="review-niv1-options"
                    value={niv1}
                    placeholder="Choisir ou saisir un thème…"
                    hint="Liste déroulante, ou tapez un nouveau thème."
                    autoComplete="off"
                    onChange={(e) => setNiv1(e.target.value)}
                    onBlur={realignNiv2OnBlur}
                  />
                  <Input
                    label="Sous-thème niv.2"
                    list="review-niv2-options"
                    value={niv2}
                    placeholder="Choisir ou saisir un sous-thème…"
                    hint="Liste déroulante, ou tapez un nouveau sous-thème."
                    autoComplete="off"
                    onChange={(e) => setNiv2(e.target.value)}
                  />
                  <datalist id="review-niv1-options">
                    {themes.map((t) => <option key={t.niv1} value={t.niv1} />)}
                  </datalist>
                  <datalist id="review-niv2-options">
                    {childrenOf(niv1).map((n) => <option key={n} value={n} />)}
                  </datalist>
                </div>
                <Select label="Sentiment" value={sentiment} onChange={(e) => setSentiment(e.target.value)}>
                  {SENTIMENTS.map((s) => <option key={s}>{s}</option>)}
                </Select>

                <div className="ui-field">
                  <span className="ui-field__label">Signaux</span>
                  <div className="ui-row ui-row--wrap">
                    <Chip active={sigR} onClick={() => setSigR(!sigR)}>Rupture client</Chip>
                    <Chip active={sigC} onClick={() => setSigC(!sigC)}>Churn</Chip>
                    <Chip active={sigI} onClick={() => setSigI(!sigI)}>Insatisfaction forte</Chip>
                  </div>
                </div>

                <div className="ui-row" style={{ marginTop: "var(--sp-2)" }}>
                  <Button variant="secondary" loading={busy} onClick={() => submit("validate")}>
                    Valider tel quel <kbd className="ui-kbd">V</kbd>
                  </Button>
                  <Button variant="primary" loading={busy} onClick={() => submit("correct")}>
                    Corriger &amp; valider <kbd className="ui-kbd">C</kbd>
                  </Button>
                </div>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
