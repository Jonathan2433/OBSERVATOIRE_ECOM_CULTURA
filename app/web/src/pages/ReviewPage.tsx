import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  correctResult, exportCorrectionsUrl, getFilteredReviewQueue, getTaxonomy,
  type ResultRow, type TaxonomyTheme,
} from "../api";
import { Badge, Button, Card, Chip, EmptyState, Input, ProgressBar, Select, Spinner } from "../ui";
import { useAnalysisFilters } from "../analysisFilters";
import AnalysisFiltersBar from "../components/AnalysisFiltersBar";
import { SOURCE_LABELS } from "../satisfactionDisplay";

const SENTIMENTS = ["Négatif", "Neutre", "Positif"];
// Valeur sentinelle de la liste déroulante : bascule le champ en saisie libre.
const OTHER = "__AUTRE__";
const OTHER_LABEL = "Autre (saisie manuelle)";

interface ThemeDraft {
  niv1: string;
  niv2: string;
  sentiment: string;
  niv1Manual: boolean;
  niv2Manual: boolean;
}

const emptyTheme = (): ThemeDraft => ({
  niv1: "", niv2: "", sentiment: "Neutre", niv1Manual: false, niv2Manual: false,
});

const norm = (s: string) => s.trim().toLowerCase();

function formatResponseDate(value?: string | null): string {
  if (!value) return "Date non disponible";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

/** Éditeur réutilisé pour le thème principal et le second thème. */
function ThemeEditor({
  title, themes, value, onChange, onRemove,
}: {
  title: string;
  themes: TaxonomyTheme[];
  value: ThemeDraft;
  onChange: (next: ThemeDraft) => void;
  onRemove?: () => void;
}) {
  const childrenOf = (n1: string) =>
    themes.find((t) => norm(t.niv1) === norm(n1))?.niv2 ?? [];
  const canonNiv1 = (v: string) => themes.find((t) => norm(t.niv1) === norm(v))?.niv1;
  const niv2Options = childrenOf(value.niv1);
  const niv1IsOther = value.niv1Manual || (!!value.niv1 && canonNiv1(value.niv1) === undefined);
  const niv2IsOther = niv1IsOther || value.niv2Manual ||
    (!!value.niv2 && !niv2Options.some((c) => norm(c) === norm(value.niv2)));

  const onNiv1Select = (selected: string) => {
    if (selected === OTHER) {
      onChange({ ...value, niv1Manual: true, niv1: "", niv2Manual: true, niv2: "" });
      return;
    }
    const kids = childrenOf(selected);
    onChange({
      ...value,
      niv1Manual: false,
      niv1: selected,
      niv2Manual: false,
      niv2: kids.some((c) => norm(c) === norm(value.niv2)) ? value.niv2 : (kids[0] ?? ""),
    });
  };

  const onNiv2Select = (selected: string) => {
    if (selected === OTHER) onChange({ ...value, niv2Manual: true, niv2: "" });
    else onChange({ ...value, niv2Manual: false, niv2: selected });
  };

  return (
    <div className="ui-stack" style={{ gap: "var(--sp-3)", padding: "var(--sp-4)", border: "1px solid var(--cu-neutral-200)", borderRadius: "var(--r-lg)" }}>
      <div className="ui-row">
        <strong>{title}</strong>
        <div className="ui-spacer" />
        {onRemove && <Button variant="ghost" size="sm" onClick={onRemove}>Supprimer le second thème</Button>}
      </div>
      <div className="ui-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="ui-stack" style={{ gap: "var(--sp-2)" }}>
          <Select
            label="Thème niv.1"
            value={niv1IsOther ? OTHER : (canonNiv1(value.niv1) ?? value.niv1)}
            onChange={(e) => onNiv1Select(e.target.value)}
          >
            {themes.map((t) => <option key={t.niv1} value={t.niv1}>{t.niv1}</option>)}
            <option value={OTHER}>{OTHER_LABEL}</option>
          </Select>
          {niv1IsOther && (
            <Input
              aria-label={`Nouveau thème — ${title}`}
              placeholder="Saisir un nouveau thème"
              value={value.niv1}
              autoFocus={value.niv1Manual}
              autoComplete="off"
              onChange={(e) => onChange({ ...value, niv1: e.target.value })}
            />
          )}
        </div>

        <div className="ui-stack" style={{ gap: "var(--sp-2)" }}>
          <Select
            label="Sous-thème niv.2"
            value={niv2IsOther ? OTHER : (niv2Options.find((c) => norm(c) === norm(value.niv2)) ?? value.niv2)}
            onChange={(e) => onNiv2Select(e.target.value)}
          >
            {niv2Options.map((n) => <option key={n} value={n}>{n}</option>)}
            <option value={OTHER}>{OTHER_LABEL}</option>
          </Select>
          {niv2IsOther && (
            <Input
              aria-label={`Nouveau sous-thème — ${title}`}
              placeholder="Saisir un nouveau sous-thème"
              value={value.niv2}
              autoComplete="off"
              onChange={(e) => onChange({ ...value, niv2: e.target.value })}
            />
          )}
        </div>
      </div>
      <Select label={`Sentiment — ${title.toLowerCase()}`} value={value.sentiment}
              onChange={(e) => onChange({ ...value, sentiment: e.target.value })}>
        {SENTIMENTS.map((s) => <option key={s}>{s}</option>)}
      </Select>
    </div>
  );
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

  const [primary, setPrimary] = useState<ThemeDraft>(emptyTheme);
  const [secondary, setSecondary] = useState<ThemeDraft>(emptyTheme);
  const [secondaryEnabled, setSecondaryEnabled] = useState(false);
  const [sigR, setSigR] = useState(false);
  const [sigC, setSigC] = useState(false);
  const [sigI, setSigI] = useState(false);

  const loadNext = () => {
    getFilteredReviewQueue(batchId, analysisFilters, 0, 1)
      .then((r) => {
        setLoaded(true);
        setRemaining(r.total);
        if (initialTotal.current === 0 && r.total > 0) initialTotal.current = r.total;
        const it = r.items[0] ?? null;
        setItem(it);
        if (it) {
          setPrimary({
            niv1: it.theme1_niv1 ?? "", niv2: it.theme1_niv2 ?? "",
            sentiment: it.theme1_sentiment ?? "Neutre", niv1Manual: false, niv2Manual: false,
          });
          setSecondary({
            niv1: it.theme2_niv1 ?? "", niv2: it.theme2_niv2 ?? "",
            sentiment: it.theme2_sentiment ?? "Neutre", niv1Manual: false, niv2Manual: false,
          });
          setSecondaryEnabled(!!it.theme2_niv1);
          setSigR(it.signal_rupture); setSigC(it.signal_churn); setSigI(it.signal_insatisfaction);
        }
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

  const enableSecondary = () => {
    const first = themes[0];
    setSecondary(first
      ? { niv1: first.niv1, niv2: first.niv2[0] ?? "", sentiment: "Neutre", niv1Manual: false, niv2Manual: false }
      : { ...emptyTheme(), niv1Manual: true, niv2Manual: true });
    setSecondaryEnabled(true);
  };

  const submit = async (action: "validate" | "correct") => {
    if (!item || busy) return;
    setBusy(true);
    setError(null);
    try {
      await correctResult(item.id, action === "validate" ? { action } : {
        action,
        theme1_niv1: primary.niv1, theme1_niv2: primary.niv2, theme1_sentiment: primary.sentiment,
        theme2_niv1: secondaryEnabled ? secondary.niv1 : "",
        theme2_niv2: secondaryEnabled ? secondary.niv2 : "",
        theme2_sentiment: secondaryEnabled ? secondary.sentiment : "",
        signal_rupture: sigR, signal_churn: sigC, signal_insatisfaction: sigI,
      });
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
  }, [item, busy, primary, secondary, secondaryEnabled, sigR, sigC, sigI]);

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

          {!item ? (
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

                <ThemeEditor title="Thème principal" themes={themes} value={primary} onChange={setPrimary} />

                {secondaryEnabled ? (
                  <ThemeEditor title="Second thème" themes={themes} value={secondary}
                               onChange={setSecondary}
                               onRemove={() => { setSecondaryEnabled(false); setSecondary(emptyTheme()); }} />
                ) : (
                  <div>
                    <Button variant="secondary" size="sm" onClick={enableSecondary}>+ Ajouter un second thème</Button>
                  </div>
                )}

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
                  <Button variant="primary" loading={busy} onClick={() => submit("correct")}
                          disabled={!primary.niv1.trim() || !primary.niv2.trim() || !primary.sentiment ||
                            (secondaryEnabled && (!secondary.niv1.trim() || !secondary.niv2.trim() || !secondary.sentiment))}>
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
