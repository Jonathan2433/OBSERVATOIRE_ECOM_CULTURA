import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getBatch, type Batch } from "../api";
import StatusBadge from "../components/StatusBadge";
import { Card, EmptyState, ProgressBar, Spinner, StatCard } from "../ui";

export default function BatchDetailPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const b = await getBatch(batchId);
        if (!active) return;
        setBatch(b);
        if (b.status === "pending" || b.status === "running") timer = setTimeout(tick, 1500);
      } catch (e: any) {
        if (active) setError(e?.message ?? "Erreur");
      }
    };
    tick();
    return () => { active = false; clearTimeout(timer); };
  }, [batchId]);

  if (error) {
    return <EmptyState title="Lot introuvable" description={error} action={<Link className="ui-btn ui-btn--secondary ui-btn--md" to="/lots">Retour aux lots</Link>} />;
  }
  if (!batch) return <Spinner label="Chargement du lot…" />;

  const pct = batch.n_total ? Math.round((batch.n_processed / batch.n_total) * 100) : 0;
  const running = batch.status === "pending" || batch.status === "running";
  const reviewPct = batch.n_total ? Math.round((batch.n_review / batch.n_total) * 100) : 0;

  return (
    <div>
      <div className="page-header">
        <div className="ui-row">
          <h1 className="page-header__title">Lot #{batch.id} — {batch.label}</h1>
          <StatusBadge status={batch.status} />
        </div>
        <p className="page-header__sub">{batch.model_label ? `Modèle : ${batch.model_label}` : "Modèle non renseigné"}</p>
      </div>

      <div className="ui-stack">
        {running && (
          <Card title="Traitement en cours">
            <div className="ui-stack">
              <ProgressBar value={pct} indeterminate={batch.status === "pending"} />
              <span className="ui-muted">{batch.n_processed} / {batch.n_total || "?"} verbatims traités</span>
            </div>
          </Card>
        )}

        {batch.status === "failed" && (
          <Card title="Échec du traitement">
            <p className="ui-field__error">{batch.error_message || "Erreur inconnue."}</p>
          </Card>
        )}

        <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
          <StatCard label="Verbatims traités" value={batch.n_total || "—"} />
          <StatCard label="En revue humaine" value={batch.status === "done" ? batch.n_review : "—"}
                    hint={batch.status === "done" ? `${reviewPct} %` : undefined} />
          <StatCard label="Erreurs" value={batch.n_errors} />
          <StatCard label="Durée" value={batch.duration_s != null ? `${batch.duration_s.toFixed(1)} s` : "—"} />
          <StatCard label="Seuil de revue" value={batch.seuil_revue.toFixed(2)} />
        </div>

        {batch.status === "done" && (
          <Card title="Exploiter ce lot">
            <div className="ui-row ui-row--wrap">
              <Link className="ui-btn ui-btn--primary ui-btn--md" to={`/lots/${batch.id}/resultats`}>Résultats &amp; export</Link>
              <Link className="ui-btn ui-btn--secondary ui-btn--md" to={`/lots/${batch.id}/kpi`}>Tableau de bord</Link>
              <Link className="ui-btn ui-btn--secondary ui-btn--md" to={`/lots/${batch.id}/revue`}>Revue humaine ({batch.n_review})</Link>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
