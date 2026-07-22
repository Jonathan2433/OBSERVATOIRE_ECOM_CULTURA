import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { exportUrl, listResults, type ResultFilters, type ResultRow, type ResultsResponse } from "../api";
import { Badge, type BadgeTone, Button, Card, Chip, Drawer, EmptyState, InfoTip, Input, Select, Spinner } from "../ui";

const PAGE = 50;

function sentimentTone(s?: string | null): BadgeTone {
  return s === "Négatif" ? "danger" : s === "Positif" ? "success" : "neutral";
}

function SignalBadges({ r }: { r: ResultRow }) {
  const out = [];
  if (r.signal_rupture) out.push(<Badge key="r" tone="danger">rupture</Badge>);
  if (r.signal_churn) out.push(<Badge key="c" tone="warning">churn</Badge>);
  if (r.signal_insatisfaction) out.push(<Badge key="i" tone="warning">insatisf.</Badge>);
  return out.length ? <span className="ui-row" style={{ gap: 4 }}>{out}</span> : <span className="ui-muted">—</span>;
}

export default function ResultsPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [data, setData] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<ResultFilters>({});
  const [selected, setSelected] = useState<ResultRow | null>(null);

  useEffect(() => {
    listResults(batchId, { ...filters, limit: PAGE, offset })
      .then(setData)
      .catch((e) => setError(String(e.message ?? e)));
  }, [batchId, offset, filters]);

  const apply = (patch: ResultFilters) => { setOffset(0); setFilters((f) => ({ ...f, ...patch })); };
  const toggle = (key: keyof ResultFilters) => apply({ [key]: filters[key] ? undefined : true } as ResultFilters);

  return (
    <div>
      <div className="ui-stack">
        <Card title="Filtres" actions={
          <span className="ui-row">
            <a className="ui-btn ui-btn--secondary ui-btn--sm" href={exportUrl(batchId, "csv", filters)}
               title="Exporte uniquement les lignes correspondant aux filtres actifs">Export CSV</a>
            <a className="ui-btn ui-btn--secondary ui-btn--sm" href={exportUrl(batchId, "xlsx", filters)}
               title="Exporte uniquement les lignes correspondant aux filtres actifs">Export Excel</a>
          </span>
        }>
          <div className="ui-toolbar">
            <Input placeholder="Recherche texte…" style={{ minWidth: 200 }}
                   onChange={(e) => apply({ q: e.target.value || undefined })} />
            <Input placeholder="Thème (contient…)" style={{ minWidth: 180 }}
                   onChange={(e) => apply({ niv1: e.target.value || undefined })} />
            <Select defaultValue="" onChange={(e) => apply({ sentiment: e.target.value || undefined })}>
              <option value="">Sentiment (tous)</option>
              <option>Négatif</option><option>Neutre</option><option>Positif</option>
            </Select>
            <span className="ui-toolbar__sep" />
            <Chip active={!!filters.revue} onClick={() => toggle("revue")}>En revue</Chip>
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
                        <th>Verbatim (anonymisé)</th><th>Thème</th><th>Sentiment</th>
                        <th>Signaux</th>
                        <th>Confiance<InfoTip text="Certitude du modèle (0 à 1). Sous le seuil de revue, le verbatim part en relecture humaine." /></th>
                        <th>Statut<InfoTip text="auto = classé sans relecture · en revue = à vérifier · corrigé = revu par un humain." /></th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((r) => (
                        <tr key={r.id} className="is-clickable" onClick={() => setSelected(r)}>
                          <td style={{ maxWidth: 340 }}>{r.verbatim_analyse.slice(0, 120)}{r.verbatim_analyse.length > 120 ? "…" : ""}</td>
                          <td>{r.theme1_niv1 ? <>{r.theme1_niv1}<br /><span className="ui-muted">{r.theme1_niv2}</span></> : "—"}</td>
                          <td><Badge tone={sentimentTone(r.theme1_sentiment)}>{r.theme1_sentiment ?? "—"}</Badge></td>
                          <td><SignalBadges r={r} /></td>
                          <td className="ui-table__num">{r.confidence_globale != null ? r.confidence_globale.toFixed(2) : "—"}</td>
                          <td>{r.corrected ? <Badge tone="primary">corrigé</Badge> : r.revue_requise ? <Badge tone="warning" dot>en revue</Badge> : <Badge tone="success" dot>auto</Badge>}</td>
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

      <Drawer open={!!selected} title={selected ? `Verbatim #${selected.row_index}` : ""} onClose={() => setSelected(null)}>
        {selected && (
          <div className="ui-stack">
            <div className="ui-verbatim">{selected.verbatim_analyse}</div>
            <dl className="ui-dl">
              <dt>Source</dt><dd>{selected.source ?? "—"}</dd>
              <dt>Thème 1</dt><dd>{selected.theme1_niv1 ? `${selected.theme1_niv1} / ${selected.theme1_niv2}` : "—"}{selected.theme1_score != null ? ` (${selected.theme1_score.toFixed(2)})` : ""}</dd>
              <dt>Thème 2</dt><dd>{selected.theme2_niv1 ? `${selected.theme2_niv1} / ${selected.theme2_niv2}` : "—"}</dd>
              <dt>Sentiment</dt><dd><Badge tone={sentimentTone(selected.theme1_sentiment)}>{selected.theme1_sentiment ?? "—"}</Badge></dd>
              <dt>Signaux</dt><dd><SignalBadges r={selected} /></dd>
              <dt>Confiance</dt><dd>{selected.confidence_globale != null ? selected.confidence_globale.toFixed(2) : "—"}</dd>
              <dt>Statut</dt><dd>{selected.corrected ? "corrigé" : selected.revue_requise ? "en revue" : "auto"}</dd>
            </dl>
          </div>
        )}
      </Drawer>
    </div>
  );
}
