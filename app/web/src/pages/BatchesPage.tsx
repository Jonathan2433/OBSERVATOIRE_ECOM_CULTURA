import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createBatch, getMeta, listBatches, listModels, type Batch, type ModelVersion } from "../api";
import StatusBadge from "../components/StatusBadge";
import { Button, Card, FilesDropzone, InfoTip, Input, ProgressBar, Select } from "../ui";

export default function BatchesPage() {
  const navigate = useNavigate();
  const [batches, setBatches] = useState<Batch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [seuil, setSeuil] = useState(0.5);  // remplacé par la valeur de config au montage
  // Un seul dépôt pour tout le mois : la source de chaque fichier est
  // identifiée à la lecture, il n'y a rien à déclarer.
  const [fichiers, setFichiers] = useState<File[]>([]);
  const [refiner, setRefiner] = useState("");                 // "" = aucun (1 seul moteur)
  const [refiners, setRefiners] = useState<ModelVersion[]>([]); // raffineurs LLM locaux dispo

  const refresh = () => listBatches().then(setBatches).catch((e) => setError(String(e.message ?? e)));

  useEffect(() => {
    // Seuil par défaut piloté par la config (Administration), pas codé en dur.
    getMeta().then((m) => setSeuil(m.default_seuil_revue)).catch(() => {});
    // Raffineurs possibles = moteurs LLM LOCAUX disponibles (lmstudio). Claude exclu (offline).
    listModels().then((ms) => setRefiners(ms.filter((m) => m.available && m.kind === "lmstudio")))
      .catch(() => setRefiners([]));
    refresh();
    const t = setInterval(() => {
      setBatches((prev) => {
        if (prev.some((b) => b.status === "pending" || b.status === "running")) refresh();
        return prev;
      });
    }, 3000);
    return () => clearInterval(t);
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (fichiers.length === 0) {
      setError("Déposez au moins un export (MDTC ou Mopinion, .xlsx ou .csv).");
      return;
    }
    setBusy(true);
    try {
      const b = await createBatch({
        label: label.trim() || undefined, seuilRevue: seuil,
        refinerLabel: refiner || undefined, fichiers,
      });
      navigate(`/lots/${b.id}`);
    } catch (err: any) {
      setError(err?.message ?? "Erreur lors de la création du lot");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Lots de traitement</h1>
        <p className="page-header__sub">Déposez les exports du mois (Excel ou CSV, autant que nécessaire), puis lancez et suivez le traitement.</p>
      </div>

      <div className="ui-stack">
        <Card title="Nouveau lot">
          {error && <p className="ui-field__error" style={{ marginBottom: "var(--sp-3)" }}>{error}</p>}
          <form onSubmit={onSubmit} className="ui-stack" style={{ maxWidth: 720 }}>
            <FilesDropzone
              label="Exports du mois"
              hint="Glisser-déposer ou cliquer — MDTC et Mopinion, .xlsx ou .csv"
              files={fichiers} onChange={setFichiers} />
            <p className="ui-muted" style={{ margin: 0 }}>
              Déposez tous les exports du mois d'un coup — post-achat et post-réception,
              ancien et nouveau format, Mopinion desktop et mobile. Chaque fichier est
              reconnu à la lecture : rien à déclarer. Un fichier non reconnu arrête le
              lot en le nommant, plutôt que de traiter un mois incomplet en silence.
            </p>
            <Input label="Libellé du lot (optionnel)" value={label}
                   onChange={(e) => setLabel(e.target.value)} placeholder="ex. juillet 2026" />
            <label className="ui-field">
              <span className="ui-field__label">Seuil de revue humaine : <b>{seuil.toFixed(2)}</b>
                <InfoTip text="En dessous de ce score de confiance, un verbatim est envoyé en revue humaine. Plus le seuil est haut, plus de verbatims sont relus." />
              </span>
              <input className="ui-range" type="range" min={0} max={1} step={0.05} value={seuil}
                     onChange={(e) => setSeuil(parseFloat(e.target.value))} />
              <span className="ui-field__hint">En dessous de ce score de confiance, un verbatim part en revue.</span>
            </label>
            <Select label="Raffinement — 2ᵉ moteur (optionnel)" value={refiner}
                    onChange={(e) => setRefiner(e.target.value)} style={{ maxWidth: 360 }}
                    hint={refiners.length
                      ? "Le modèle actif propose, puis ce moteur LLM relit et corrige. Désaccord sur le grand thème → revue forcée."
                      : "Aucun moteur LLM local disponible (active LM Studio dans Administration → Modèles)."}
                    disabled={refiners.length === 0}>
              <option value="">Aucun (1 seul moteur)</option>
              {refiners.map((m) => (
                <option key={m.id} value={m.label}>{m.label}</option>
              ))}
            </Select>
            <div>
              <Button type="submit" variant="primary" loading={busy}>
                {busy ? "Lancement…" : "Lancer le traitement"}
              </Button>
            </div>
          </form>
        </Card>

        <Card title="Historique des lots">
          <div className="ui-table-wrap">
            <table className="ui-table">
              <thead>
                <tr>
                  <th>#</th><th>Libellé</th><th>Statut</th><th>Progression</th>
                  <th>Verbatims</th><th>En revue</th><th>Traité le</th><th>Modèle</th>
                </tr>
              </thead>
              <tbody>
                {batches.length === 0 && (
                  <tr><td colSpan={8} className="ui-table__empty">Aucun lot pour l'instant.</td></tr>
                )}
                {batches.map((b) => {
                  const pct = b.n_total ? Math.round((b.n_processed / b.n_total) * 100) : 0;
                  const active = b.status === "running" || b.status === "pending";
                  return (
                    <tr key={b.id} className="is-clickable" onClick={() => navigate(`/lots/${b.id}`)}>
                      <td className="ui-table__num">{b.id}</td>
                      <td>{b.label}</td>
                      <td><StatusBadge status={b.status} /></td>
                      <td style={{ minWidth: 140 }}>
                        {active ? <ProgressBar value={pct} indeterminate={b.status === "pending"} /> : "—"}
                      </td>
                      <td className="ui-table__num">{b.n_total || "—"}</td>
                      <td className="ui-table__num">{b.status === "done" ? b.n_review : "—"}</td>
                      <td className="ui-muted">{b.finished_at
                        ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(b.finished_at))
                        : "—"}</td>
                      <td className="ui-muted">{b.model_label ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
