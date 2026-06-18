import { useEffect, useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
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

  if (error) return <EmptyState title="Lot introuvable" description={error} />;
  if (!batch) return <Spinner label="Chargement du lot…" />;

  const pct = batch.n_total ? Math.round((batch.n_processed / batch.n_total) * 100) : 0;
  const running = batch.status === "pending" || batch.status === "running";
  const reviewPct = batch.n_total ? Math.round((batch.n_review / batch.n_total) * 100) : 0;

  const tabClass = ({ isActive }: { isActive: boolean }) => "ui-tab" + (isActive ? " is-active" : "");

  return (
    <div>
      <div className="page-header">
        <div className="ui-row">
          <h1 className="page-header__title">Lot #{batch.id} — {batch.label}</h1>
          <StatusBadge status={batch.status} />
        </div>
        <p className="page-header__sub">{batch.model_label ? `Modèle : ${batch.model_label}` : "Modèle non renseigné"}</p>
      </div>

      {running && (
        <Card title="Traitement en cours" className="">
          <div className="ui-stack">
            <ProgressBar value={pct} indeterminate={batch.status === "pending"} />
            <span className="ui-muted">{batch.n_processed} / {batch.n_total || "?"} verbatims traités — cette page se met à jour automatiquement.</span>
          </div>
        </Card>
      )}

      {batch.status === "failed" && (
        <Card title="Échec du traitement"><p className="ui-field__error">{batch.error_message || "Erreur inconnue."}</p></Card>
      )}

      {batch.status === "done" ? (
        <>
          <nav className="ui-tabs" aria-label="Vues du lot">
            <NavLink to="." end className={tabClass}>Tableau de bord</NavLink>
            <NavLink to="resultats" className={tabClass}>Résultats</NavLink>
            <NavLink to="revue" className={tabClass}>
              Revue {batch.n_review > 0 && <span className="ui-tab__count">{batch.n_review}</span>}
            </NavLink>
          </nav>
          <Outlet />
        </>
      ) : !running && (
        <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
          <StatCard label="Verbatims" value={batch.n_total || "—"} />
          <StatCard label="En revue" value={batch.n_review} hint={`${reviewPct} %`} />
          <StatCard label="Erreurs" value={batch.n_errors} />
        </div>
      )}
    </div>
  );
}
