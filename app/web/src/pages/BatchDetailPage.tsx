import { useEffect, useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { cancelBatch, getBatch, type Batch } from "../api";
import StatusBadge from "../components/StatusBadge";
import { Badge, Button, Card, Dialog, EmptyState, ProgressBar, Spinner, StatCard } from "../ui";

export default function BatchDetailPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [cancelling, setCancelling] = useState(false);

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

  const doCancel = async () => {
    setCancelling(true);
    try {
      const b = await cancelBatch(batchId);
      setBatch(b);
    } catch (e: any) {
      setError(e?.message ?? "Annulation impossible");
    } finally {
      setCancelling(false);
      setConfirmCancel(false);
    }
  };

  const tabClass = ({ isActive }: { isActive: boolean }) => "ui-tab" + (isActive ? " is-active" : "");

  return (
    <div>
      <div className="page-header">
        <div className="ui-row">
          <h1 className="page-header__title">Lot #{batch.id} — {batch.label}</h1>
          <StatusBadge status={batch.status} />
          {batch.refiner_label && <Badge tone="info" dot>cascade</Badge>}
        </div>
        <p className="page-header__sub">{batch.model_label ? `Modèle : ${batch.model_label}` : "Modèle non renseigné"}</p>
        {batch.refiner_label && batch.chain_disagreements != null && (
          <p className="page-header__sub">
            Cascade : <b>{batch.chain_disagreements}</b> désaccord(s) proposeur/raffineur sur <code>theme1_niv1</code> → revue forcée.
          </p>
        )}
      </div>

      {running && (
        <Card title="Traitement en cours" actions={
          <Button variant="danger" size="sm" onClick={() => setConfirmCancel(true)}>Annuler</Button>
        }>
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
            <NavLink to="comparaison" className={tabClass}>Comparaison</NavLink>
          </nav>
          <Outlet />
        </>
      ) : !running && (
        <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
          <StatCard label="Verbatims" value={batch.n_total || "—"} />
          <StatCard label="En revue" value={batch.n_review} hint={`${reviewPct} %`} />
          <StatCard label="Erreurs" value={batch.n_errors} />
          {batch.refiner_label && (
            <StatCard label="Désaccords cascade" value={batch.chain_disagreements ?? 0}
                      hint="proposeur ≠ raffineur (revue forcée)" />
          )}
        </div>
      )}

      <Dialog
        open={confirmCancel} danger busy={cancelling}
        title="Annuler ce lot ?" confirmLabel="Annuler le lot" cancelLabel="Continuer"
        onConfirm={doCancel} onCancel={() => setConfirmCancel(false)}
      >
        <p>Le traitement s'arrêtera proprement. Les résultats déjà calculés sont conservés ; le lot passe au statut « annulé ».</p>
      </Dialog>
    </div>
  );
}
