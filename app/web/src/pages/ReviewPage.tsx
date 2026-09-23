import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  correctResult, exportCorrectionsUrl, getFilteredReviewQueue, getTaxonomy,
  type ResultRow, type TaxonomyTheme,
} from "../api";
import { Badge, Button, Card, EmptyState, ProgressBar, Spinner } from "../ui";
import { useAnalysisFilters } from "../analysisFilters";
import AnalysisFiltersBar from "../components/AnalysisFiltersBar";
import {
  buildCorrectionPayload, CorrectionFields, draftFromResult, isCorrectionValid, type CorrectionDraft,
} from "../components/CorrectionForm";
import { SOURCE_LABELS } from "../satisfactionDisplay";

function formatResponseDate(value?: string | null): string {
  if (!value) return "Date non disponible";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

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
  const { filters: analysisFilters, setFilters: setAnalysisFilters } = useAnalysisFilters();

  const [draft, setDraft] = useState<CorrectionDraft | null>(null);

  const loadNext = () => {
    getFilteredReviewQueue(batchId, analysisFilters, 0, 1)
      .then((r) => {
        setLoaded(true);
        setRemaining(r.total);
        if (initialTotal.current === 0 && r.total > 0) initialTotal.current = r.total;
        const it = r.items[0] ?? null;
        setItem(it);
        setDraft(it ? draftFromResult(it) : null);
      })
      .catch((e) => setError(String(e.message ?? e)));
  };

  useEffect(() => {
    setLoaded(false);
    initialTotal.current = 0;
    getTaxonomy(batchId).then((t) => setThemes(t.themes)).catch(() => setThemes([]));
    loadNext();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId, analysisFilters]);

  const submit = async (action: "validate" | "correct") => {
    if (!item || !draft || busy) return;
    setBusy(true);
    setError(null);
    try {
      await correctResult(item.id, buildCorrectionPayload(draft, action));
      // Une correction a pu introduire un nouveau thème/sous-thème : on rafraîchit
      // le référentiel pour qu'il soit proposé sur les verbatims suivants.
      if (action === "correct") {
        getTaxonomy(batchId).then((t) => setThemes(t.themes)).catch(() => { /* garde l'ancien */ });
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
  }, [item, draft, busy]);

  const done = Math.max(0, initialTotal.current - remaining);
  const pct = initialTotal.current ? Math.round((done / initialTotal.current) * 100) : 0;

  return (
    <div>
      <AnalysisFiltersBar filters={analysisFilters} onChange={setAnalysisFilters} />
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

          {!item || !draft ? (
            <EmptyState title="File de revue vide ✓" description="Tous les verbatims incertains de ce lot ont été traités." />
          ) : (
            <Card title={`Verbatim #${item.row_index}`}>
              <div className="ui-stack">
                <section className="review-context" aria-label="Contexte du retour client">
                  <div className="review-context__source">
                    <span className="ui-field__label">Contexte du retour</span>
                    <Badge tone="info">
                      {SOURCE_LABELS[item.source ?? ""] ?? item.source ?? "Source non disponible"}
                    </Badge>
                  </div>
                  <dl className="review-context__details">
                    <div>
                      <dt>Fichier source</dt>
                      <dd title={item.source_file ?? undefined}>{item.source_file ?? "Non disponible"}</dd>
                    </div>
                    <div>
                      <dt>Référence réponse</dt>
                      <dd><code>{item.response_reference ?? "Non disponible"}</code></dd>
                    </div>
                    <div>
                      <dt>Date du retour</dt>
                      <dd>{formatResponseDate(item.response_date)}</dd>
                    </div>
                  </dl>
                </section>
                <div className="ui-verbatim" style={{ fontStyle: "italic" }}>« {item.verbatim_analyse} »</div>
                <div className="ui-row ui-row--wrap" style={{ fontSize: "var(--fs-sm)" }}>
                  <span className="ui-muted">Proposition modèle :</span>
                  <Badge tone="neutral">1 · {item.theme1_niv1} / {item.theme1_niv2}</Badge>
                  <Badge tone="neutral">{item.theme1_sentiment}</Badge>
                  {item.theme2_niv1 && (
                    <>
                      <Badge tone="info">2 · {item.theme2_niv1} / {item.theme2_niv2}</Badge>
                      <Badge tone="info">{item.theme2_sentiment || "sentiment non renseigné"}</Badge>
                    </>
                  )}
                  <span className="ui-muted">confiance {item.confidence_globale?.toFixed(2)}</span>
                </div>

                <CorrectionFields themes={themes} draft={draft} onChange={setDraft} />

                <div className="ui-row" style={{ marginTop: "var(--sp-2)" }}>
                  <Button variant="secondary" loading={busy} onClick={() => submit("validate")}>
                    Valider tel quel <kbd className="ui-kbd">V</kbd>
                  </Button>
                  <Button variant="primary" loading={busy} onClick={() => submit("correct")}
                          disabled={!isCorrectionValid(draft)}>
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
