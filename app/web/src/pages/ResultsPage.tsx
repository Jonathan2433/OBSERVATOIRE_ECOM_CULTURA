import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  correctResult, exportUrl, getMeta, getTaxonomy, listResults,
  type ResultFilters, type ResultRow, type ResultsResponse, type TaxonomyTheme,
} from "../api";
import { Badge, type BadgeTone, Button, Card, Chip, Drawer, EmptyState, InfoTip, Input, Select, Spinner } from "../ui";
import { CLIENT_STATUS_LABELS, satisfactionOnTen, SOURCE_LABELS } from "../satisfactionDisplay";
import { useAnalysisFilters } from "../analysisFilters";
import AnalysisFiltersBar from "../components/AnalysisFiltersBar";
import {
  buildCorrectionPayload, CorrectionFields, draftFromResult, isCorrectionValid, type CorrectionDraft,
} from "../components/CorrectionForm";

const PAGE = 50;

function formatDate(value?: string | null, withTime = false): string {
  if (!value) return "—";
  const normalized = value.length === 10 ? `${value}T00:00:00Z` : value;
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    timeZone: withTime ? "Europe/Paris" : "UTC",
  }).format(new Date(normalized));
}

function sentimentTone(s?: string | null): BadgeTone {
  return s === "Négatif" ? "danger" : s === "Positif" ? "success" : "neutral";
}

/**
 * Note déposée par le client, conservée sur son échelle native.
 *
 * Distincte du signal « insatisf. » juste à côté, qui est une DÉDUCTION du
 * modèle sur le texte. Les deux divergent régulièrement — un client peut noter
 * 4 et écrire un irritant — et c'est l'écart qui intéresse le pilotage.
 *
 * Une note absente s'affiche « — », jamais 0 : les lots traités avant que la
 * note ne soit conservée n'en portent aucune.
 */
function SatisfactionPill({ note, scale, compact = false }: {
  note?: number | null;
  scale?: number | null;
  compact?: boolean;
}) {
  if (note == null || scale == null) return (
    <span className="ui-muted" title="Détail natif indisponible">
      {compact ? "—" : "détail natif indisponible"}
    </span>
  );
  const onTen = satisfactionOnTen(note, scale);
  return <Badge tone="info">{note}/{scale} · {onTen.toFixed(1)}/10</Badge>;
}

/**
 * Thèmes d'un verbatim : le principal, puis le SECOND s'il existe.
 *
 * La couche de décision retient jusqu'à deux thèmes ; n'afficher que le premier
 * revenait à jeter à l'écran une information que le modèle produit, que
 * l'export contient et que les répartitions comptent. Le second est marqué
 * « 2e » pour qu'aucune lecture ne confonde les deux rangs.
 */
function ClassificationCell({ r }: { r: ResultRow }) {
  if (!r.theme1_niv1) return <>—</>;
  return (
    <div className="result-classifications">
      <div className="result-classification">
        <div className="ui-row ui-row--wrap" style={{ gap: 4 }}>
          <strong>{r.theme1_niv1}</strong>
          <Badge tone={sentimentTone(r.theme1_sentiment)}>{r.theme1_sentiment ?? "—"}</Badge>
        </div>
        {r.theme1_niv2 && <><br /><span className="ui-muted">{r.theme1_niv2}</span></>}
      </div>
      {r.theme2_niv1 && (
        <div className="result-classification result-classification--secondary">
          <span className="ui-row ui-row--wrap" style={{ gap: 4 }}>
            <Badge tone="info">2e</Badge>
            <strong>{r.theme2_niv1}</strong>
            <Badge tone={sentimentTone(r.theme2_sentiment)}>{r.theme2_sentiment ?? "—"}</Badge>
          </span>
          {r.theme2_niv2 && <><br /><span className="ui-muted">{r.theme2_niv2}</span></>}
        </div>
      )}
    </div>
  );
}

/**
 * Signaux d'un résultat.
 *
 * Un signal sans détecteur entraîné (D-41 : `churn` 64 positifs au corpus,
 * `rupture` 32) sort TOUJOURS à `false`. Ne rien afficher le ferait lire comme
 * « pas de rupture détectée », alors que nous ne l'avons pas cherchée —
 * arbitrage PO du 11/09 : l'écran doit dire « non mesuré ».
 *
 * `nonMesures` vient de /api/meta. Vide (méta indisponible), le composant
 * retrouve son comportement d'origine : on n'invente pas un périmètre.
 */
function SignalBadges({ r, nonMesures = [] }: { r: ResultRow; nonMesures?: string[] }) {
  const mesure = (nom: string) => !nonMesures.includes(nom);
  const out = [];
  if (mesure("rupture") && r.signal_rupture) out.push(<Badge key="r" tone="danger">rupture</Badge>);
  if (mesure("churn") && r.signal_churn) out.push(<Badge key="c" tone="warning">churn</Badge>);
  if (mesure("insatisfaction") && r.signal_insatisfaction) out.push(<Badge key="i" tone="warning">insatisf.</Badge>);

  const absents = ["rupture", "churn", "insatisfaction"].filter((n) => nonMesures.includes(n));
  return (
    <span className="ui-row" style={{ gap: 4 }}>
      {out.length ? out : (absents.length < 3 ? <span className="ui-muted">—</span> : null)}
      {absents.length > 0 && (
        <span className="ui-row" style={{ gap: 4 }}>
          <Badge tone="neutral">{absents.join(", ")} : non mesuré</Badge>
          <InfoTip text={`Aucun détecteur n'est entraîné pour ${absents.join(" et ")} : trop peu d'exemples dans le corpus annoté pour un modèle évaluable (D-41). Ces signaux ne sont pas « absents », ils ne sont pas recherchés. La règle métier reste à définir.`} />
        </span>
      )}
    </span>
  );
}

export default function ResultsPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [data, setData] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<ResultFilters>({});
  const [selected, setSelected] = useState<ResultRow | null>(null);
  const { filters: analysisFilters, setFilters: setAnalysisFilters } = useAnalysisFilters();
  // Périmètre de mesure des signaux (D-41). Échec silencieux : sans cette
  // information l'affichage retombe sur son comportement d'origine.
  const [nonMesures, setNonMesures] = useState<string[]>([]);

  // Correction depuis Résultats : référentiel du lot (D31, jamais celui du
  // moteur actif) + brouillon d'édition du verbatim ouvert dans le Drawer.
  const [themes, setThemes] = useState<TaxonomyTheme[]>([]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<CorrectionDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    getMeta().then((m) => setNonMesures(m.signaux_non_mesures ?? [])).catch(() => {});
  }, []);

  useEffect(() => {
    getTaxonomy(batchId).then((t) => setThemes(t.themes)).catch(() => setThemes([]));
  }, [batchId]);

  const openDetail = (r: ResultRow) => {
    setSelected(r);
    setEditing(false);
    setDraft(null);
    setSaveError(null);
  };
  const closeDetail = () => {
    setSelected(null);
    setEditing(false);
    setDraft(null);
    setSaveError(null);
  };
  const startEdit = () => {
    if (!selected) return;
    setDraft(draftFromResult(selected));
    setSaveError(null);
    setEditing(true);
  };
  const cancelEdit = () => {
    setEditing(false);
    setDraft(null);
    setSaveError(null);
  };
  const saveEdit = async () => {
    if (!selected || !draft || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await correctResult(selected.id, buildCorrectionPayload(draft, "correct"));
      setData((d) => (d ? { ...d, items: d.items.map((it) => (it.id === updated.id ? updated : it)) } : d));
      setSelected(updated);
      setEditing(false);
      setDraft(null);
      // La correction a pu introduire un nouveau couple thème/sous-thème.
      getTaxonomy(batchId).then((t) => setThemes(t.themes)).catch(() => { /* garde l'ancien */ });
    } catch (e: any) {
      setSaveError(e?.message ?? "Erreur");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    listResults(batchId, { ...filters, ...analysisFilters, limit: PAGE, offset })
      .then(setData)
      .catch((e) => setError(String(e.message ?? e)));
  }, [batchId, offset, filters, analysisFilters]);

  const apply = (patch: ResultFilters) => { setOffset(0); setFilters((f) => ({ ...f, ...patch })); };
  const toggle = (key: keyof ResultFilters) => apply({ [key]: filters[key] ? undefined : true } as ResultFilters);

  return (
    <div>
      <div className="ui-stack">
        <AnalysisFiltersBar filters={analysisFilters} onChange={(next) => {
          setOffset(0);
          setAnalysisFilters(next);
        }} />
        <Card title="Filtres" actions={
          <span className="ui-row">
            <a className="ui-btn ui-btn--secondary ui-btn--sm" href={exportUrl(batchId, "csv", { ...filters, ...analysisFilters })}
               title="Exporte uniquement les lignes correspondant aux filtres actifs">Export CSV</a>
            <a className="ui-btn ui-btn--secondary ui-btn--sm" href={exportUrl(batchId, "xlsx", { ...filters, ...analysisFilters })}
               title="Exporte uniquement les lignes correspondant aux filtres actifs">Export Excel</a>
          </span>
        }>
          <div className="ui-toolbar">
            <Input placeholder="Recherche texte…" style={{ minWidth: 200 }}
                   onChange={(e) => apply({ q: e.target.value || undefined })} />
            <span className="ui-row" style={{ gap: 4 }}>
              <Input placeholder="Thème (contient…)" style={{ minWidth: 180 }}
                     onChange={(e) => apply({ niv1: e.target.value || undefined })} />
              <InfoTip text="Cherche dans les quatre champs de thème : niveau 1 et niveau 2, du thème principal comme du second. Un verbatim qui n'évoque le sujet qu'en second thème est donc ramené." />
            </span>
            <Select defaultValue="" onChange={(e) => apply({ sentiment: e.target.value || undefined })}>
              <option value="">Sentiment (tous)</option>
              <option>Négatif</option><option>Neutre</option><option>Positif</option>
            </Select>
            <span className="ui-toolbar__sep" />
            <Chip active={!!filters.revue} onClick={() => toggle("revue")}>En revue</Chip>
            <Chip active={!!filters.bi_theme} onClick={() => toggle("bi_theme")}>Bi-thème</Chip>
            <Chip active={!!filters.rupture} onClick={() => toggle("rupture")}>Rupture</Chip>
            <Chip active={!!filters.churn} onClick={() => toggle("churn")}>Churn</Chip>
            <Chip active={!!filters.insatisfaction} onClick={() => toggle("insatisfaction")}>Insatisfaction</Chip>
          </div>
        </Card>

        {error && <p className="ui-field__error">{error}</p>}
        {!data && !error && <Spinner label="Chargement des résultats…" />}

        {data && (
          <Card title={`${data.total} résultat(s)`}>
            {data.total === 0 ? (
              <EmptyState title="Aucun résultat" description="Aucun verbatim ne correspond à ces filtres." />
            ) : (
              <>
                <div className="ui-table-wrap">
                  <table className="ui-table">
                    <thead>
                      <tr>
                        <th>Retour client<InfoTip text="Source, verbatim anonymisé et note native du répondant lorsqu'elle est disponible." /></th>
                        <th>Classification du verbatim<InfoTip text="Analyse automatique du texte libre uniquement. Chaque thème est présenté avec son sous-thème et son propre sentiment. Le second thème est marqué « 2e ». Les réponses aux questions fermées ne sont pas incluses." /></th>
                        <th>Signaux</th>
                        <th>Fiabilité<InfoTip text="Confiance du modèle et statut : auto, en revue ou corrigé. Une prédiction automatique n'est jamais présentée comme une validation humaine." /></th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((r) => (
                        <tr key={r.id} className="is-clickable" onClick={() => openDetail(r)}>
                          <td className="result-feedback">
                            <div className="ui-row ui-row--wrap" style={{ gap: 6 }}>
                              <Badge tone="neutral">{SOURCE_LABELS[r.source ?? ""] ?? r.source ?? "source inconnue"}</Badge>
                              <SatisfactionPill note={r.satisfaction_native} scale={r.satisfaction_scale_max} compact />
                            </div>
                            <p>{r.verbatim_analyse.slice(0, 150)}{r.verbatim_analyse.length > 150 ? "…" : ""}</p>
                          </td>
                          <td><ClassificationCell r={r} /></td>
                          <td><SignalBadges r={r} nonMesures={nonMesures} /></td>
                          <td>
                            <div className="result-reliability">
                              <strong>{r.confidence_globale != null ? r.confidence_globale.toFixed(2) : "—"}</strong>
                              {r.corrected ? <Badge tone="primary">corrigé</Badge> : r.revue_requise ? <Badge tone="warning" dot>en revue</Badge> : <Badge tone="success" dot>auto</Badge>}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="ui-row" style={{ marginTop: "var(--sp-4)" }}>
                  <span className="ui-muted">Affichage {offset + 1}–{offset + data.items.length} sur {data.total}</span>
                  <div className="ui-spacer" />
                  <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>← Précédent</Button>
                  <Button variant="secondary" size="sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Suivant →</Button>
                </div>
              </>
            )}
          </Card>
        )}
      </div>

      <Drawer open={!!selected} title={selected ? `Verbatim #${selected.row_index}` : ""} onClose={closeDetail}>
        {selected && (
          <div className="ui-stack">
            <div className="ui-verbatim">{selected.verbatim_analyse}</div>

            {!editing ? (
              <>
                <dl className="ui-dl">
                  <dt>Source</dt><dd>{SOURCE_LABELS[selected.source ?? ""] ?? selected.source ?? "—"}</dd>
                  <dt>Fichier source</dt><dd>{selected.source_file ?? "—"}</dd>
                  <dt>Référence réponse</dt><dd><code>{selected.response_reference ?? "—"}</code></dd>
                  <dt>Date de publication</dt><dd>{formatDate(selected.response_date)}</dd>
                  <dt>Date de traitement du lot</dt><dd>{formatDate(selected.batch_processed_at, true)}</dd>
                  <dt>Statut client</dt><dd>{selected.client_status
                    ? CLIENT_STATUS_LABELS[selected.client_status]
                    : "Statut client non disponible"}</dd>
                  <dt>Note client</dt><dd><SatisfactionPill note={selected.satisfaction_native} scale={selected.satisfaction_scale_max} /></dd>
                  <dt>Nombre de thèmes</dt><dd>{selected.nb_themes || "—"}</dd>
                  <dt>Thème 1</dt>
                  <dd>
                    {selected.theme1_niv1 ? `${selected.theme1_niv1}${selected.theme1_niv2 ? ` / ${selected.theme1_niv2}` : ""}` : "—"}
                    {selected.theme1_score != null ? ` (${selected.theme1_score.toFixed(2)})` : ""}
                    {selected.theme1_niv1 && (
                      <> <Badge tone={sentimentTone(selected.theme1_sentiment)}>{selected.theme1_sentiment ?? "—"}</Badge></>
                    )}
                  </dd>
                  <dt>Thème 2</dt>
                  <dd>
                    {selected.theme2_niv1 ? `${selected.theme2_niv1}${selected.theme2_niv2 ? ` / ${selected.theme2_niv2}` : ""}` : "—"}
                    {selected.theme2_score != null ? ` (${selected.theme2_score.toFixed(2)})` : ""}
                    {selected.theme2_niv1 && (
                      <> <Badge tone={sentimentTone(selected.theme2_sentiment)}>{selected.theme2_sentiment ?? "—"}</Badge></>
                    )}
                  </dd>
                  <dt>Signaux</dt><dd><SignalBadges r={selected} nonMesures={nonMesures} /></dd>
                  <dt>Confiance</dt><dd>{selected.confidence_globale != null ? selected.confidence_globale.toFixed(2) : "—"}</dd>
                  <dt>Statut</dt><dd>{selected.corrected ? "corrigé" : selected.revue_requise ? "en revue" : "auto"}</dd>
                </dl>
                <div className="ui-row">
                  <div className="ui-spacer" />
                  <Button variant="secondary" size="sm" onClick={startEdit}>Corriger</Button>
                </div>
              </>
            ) : draft && (
              <div className="ui-stack">
                <div className="ui-row ui-row--wrap" style={{ fontSize: "var(--fs-sm)" }}>
                  <span className="ui-muted">Classification actuelle :</span>
                  <Badge tone="neutral">1 · {selected.theme1_niv1} / {selected.theme1_niv2}</Badge>
                  <Badge tone="neutral">{selected.theme1_sentiment}</Badge>
                  {selected.theme2_niv1 && (
                    <>
                      <Badge tone="info">2 · {selected.theme2_niv1} / {selected.theme2_niv2}</Badge>
                      <Badge tone="info">{selected.theme2_sentiment || "sentiment non renseigné"}</Badge>
                    </>
                  )}
                  <span className="ui-muted">confiance {selected.confidence_globale?.toFixed(2) ?? "—"}</span>
                </div>

                <CorrectionFields themes={themes} draft={draft} onChange={setDraft} />

                {saveError && <p className="ui-field__error">{saveError}</p>}
                <div className="ui-row" style={{ marginTop: "var(--sp-2)" }}>
                  <Button variant="ghost" disabled={saving} onClick={cancelEdit}>Annuler</Button>
                  <div className="ui-spacer" />
                  <Button variant="primary" loading={saving} disabled={!isCorrectionValid(draft)} onClick={saveEdit}>
                    Enregistrer
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
