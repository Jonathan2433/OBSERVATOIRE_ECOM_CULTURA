import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  correctResult, exportCorrectionsUrl, getReviewQueue, getTaxonomy,
  type ResultRow, type TaxonomyTheme,
} from "../api";
import { Badge, Button, Card, Chip, EmptyState, ProgressBar, Select, Spinner } from "../ui";

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

  const childrenOf = (n1: string) => themes.find((t) => t.niv1 === n1)?.niv2 ?? [];

  const onNiv1Change = (v: string) => {
    setNiv1(v);
    const kids = childrenOf(v);
    if (!kids.includes(niv2)) setNiv2(kids[0] ?? "");
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
      <div className="page-header">
        <h1 className="page-header__title">Revue humaine — lot #{batchId}</h1>
        <p className="page-header__sub">Vérifiez et corrigez les verbatims les moins confiants, du plus incertain au plus sûr.</p>
      </div>

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
                  <Select label="Thème niv.1" value={niv1} onChange={(e) => onNiv1Change(e.target.value)}>
                    {themes.map((t) => <option key={t.niv1}>{t.niv1}</option>)}
                  </Select>
                  <Select label="Sous-thème niv.2" value={niv2} onChange={(e) => setNiv2(e.target.value)}>
                    {childrenOf(niv1).map((n) => <option key={n}>{n}</option>)}
                  </Select>
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
