import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  comparisonExportUrl, createComparison, getComparison, listComparisons, listModels,
  type ComparisonRun, type ModelVersion,
} from "../api";
import { useAuth } from "../auth";
import BarList from "../components/BarList";
import StackedSentimentBar from "../components/StackedSentimentBar";
import { Badge, Button, Card, EmptyState, Input, Spinner, StatCard } from "../ui";

const KIND_LABEL: Record<string, string> = {
  real: "CamemBERT", lmstudio: "LM Studio", stub: "Démo", claude: "Claude (comparaison)",
};

export default function ComparisonPage() {
  const { id } = useParams();
  const batchId = Number(id);
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [models, setModels] = useState<ModelVersion[]>([]);
  const [runs, setRuns] = useState<ComparisonRun[]>([]);
  const [selected, setSelected] = useState<ComparisonRun | null>(null);
  const [engines, setEngines] = useState<string[]>([]);
  const [sample, setSample] = useState(50);
  const [seed, setSeed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const claudeAvailable = models.some((m) => m.kind === "claude" && m.available);

  const refreshRuns = () =>
    listComparisons(batchId).then((rs) => {
      setRuns(rs);
      setSelected((cur) => rs.find((r) => r.id === cur?.id) ?? rs[0] ?? null);
    }).catch(() => {});

  useEffect(() => {
    listModels().then((m) => setModels(m.filter((x) => x.available))).catch(() => setModels([]));
    refreshRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  // Polling tant qu'un run sélectionné est en cours.
  useEffect(() => {
    if (!selected || (selected.status !== "pending" && selected.status !== "running")) return;
    const t = setInterval(() => {
      getComparison(selected.id).then((r) => {
        setSelected(r);
        setRuns((prev) => prev.map((x) => (x.id === r.id ? r : x)));
      }).catch(() => {});
    }, 2000);
    return () => clearInterval(t);
  }, [selected]);

  const toggleEngine = (label: string) =>
    setEngines((prev) => (prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label]));

  const launch = async () => {
    setError(null);
    if (engines.length < 2) { setError("Sélectionnez au moins 2 moteurs."); return; }
    if (engines.length > 3) { setError("3 moteurs maximum."); return; }
    setBusy(true);
    try {
      const run = await createComparison(batchId, { engines, sample_size: sample, seed, judge_enabled: false });
      setRuns((prev) => [run, ...prev]);
      setSelected(run);
    } catch (e: any) {
      setError(e?.message ?? "Erreur au lancement");
    } finally {
      setBusy(false);
    }
  };

  const m = selected?.metrics ?? null;

  return (
    <div className="ui-stack">
      <Card title="Lancer une comparaison"
            actions={!isAdmin ? <Badge tone="neutral">lecture seule (admin requis)</Badge> : undefined}>
        <p className="ui-muted" style={{ marginBottom: "var(--sp-3)" }}>
          Rejoue un échantillon de ce lot à travers 2-3 moteurs et mesure leurs écarts
          (accord, confiance, latence). Le replay ne porte que sur le texte déjà anonymisé.
          {" "}Le <b>juge Claude</b> (win-rate) arrive au lot C5 — affichage en mode dégradé pour l'instant.
        </p>
        {error && <p className="ui-field__error">{error}</p>}
        <div className="ui-row ui-row--wrap" style={{ gap: "var(--sp-2)", marginBottom: "var(--sp-3)" }}>
          {models.map((mv) => (
            <button key={mv.id} type="button" disabled={!isAdmin}
                    className={"ui-chip" + (engines.includes(mv.label) ? " is-active" : "")}
                    onClick={() => toggleEngine(mv.label)}
                    style={{ cursor: isAdmin ? "pointer" : "default",
                             outline: engines.includes(mv.label) ? "2px solid var(--cu-primary-500)" : "none" }}>
              {KIND_LABEL[mv.kind] ?? mv.kind} · {mv.label}
            </button>
          ))}
        </div>
        <div className="ui-row ui-row--wrap" style={{ gap: "var(--sp-3)", alignItems: "flex-end" }}>
          <Input label="Taille d'échantillon (max 200)" type="number" min={1} max={200} value={sample}
                 onChange={(e) => setSample(Number(e.target.value))} style={{ maxWidth: 200 }} disabled={!isAdmin} />
          <Input label="Graine (reproductibilité)" type="number" value={seed}
                 onChange={(e) => setSeed(Number(e.target.value))} style={{ maxWidth: 200 }} disabled={!isAdmin} />
          <Button variant="primary" loading={busy} disabled={!isAdmin || engines.length < 2} onClick={launch}>
            {busy ? "Lancement…" : "Comparer"}
          </Button>
        </div>
        {!claudeAvailable && (
          <p className="ui-field__hint" style={{ marginTop: "var(--sp-2)" }}>
            Claude non disponible (clé absente) — comparaison entre moteurs locaux uniquement.
          </p>
        )}
      </Card>

      {runs.length > 0 && (
        <Card title="Runs de comparaison">
          <div className="ui-row ui-row--wrap" style={{ gap: "var(--sp-2)" }}>
            {runs.map((r) => (
              <button key={r.id} type="button"
                      className={"ui-chip" + (selected?.id === r.id ? " is-active" : "")}
                      onClick={() => setSelected(r)}
                      style={{ outline: selected?.id === r.id ? "2px solid var(--cu-primary-500)" : "none" }}>
                #{r.id} · {r.engine_labels.length} moteurs · n={r.sample_size} · {r.status}
              </button>
            ))}
          </div>
        </Card>
      )}

      {selected && (selected.status === "pending" || selected.status === "running") && (
        <Card title={`Run #${selected.id} — ${selected.status}`}>
          <div className="ui-row"><Spinner /> <span className="ui-muted">Comparaison en cours…</span></div>
        </Card>
      )}
      {selected && selected.status === "failed" && (
        <Card title={`Run #${selected.id} — échec`}>
          <p className="ui-field__error">{selected.error_message || "Erreur inconnue."}</p>
        </Card>
      )}

      {selected && selected.status === "done" && m && (
        <>
          <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
            <StatCard label="Échantillon" value={m.sample_size} />
            <StatCard label="Moteurs" value={m.engines.length} />
            <StatCard label="Divergences" value={m.n_divergences}
                      hint="verbatims où ≥2 moteurs diffèrent (theme niv.1)" />
          </div>

          <Card title="Taux d'accord inter-moteurs (thème niv.1)">
            <BarList data={Object.fromEntries(Object.entries(m.agreement).map(([k, v]) => [k, Math.round(v * 100)]))} />
            <p className="ui-field__hint" style={{ marginTop: "var(--sp-2)" }}>Valeurs en % d'accord sur l'échantillon.</p>
          </Card>

          <Card title="Confiance moyenne par moteur">
            <BarList data={Object.fromEntries(Object.entries(m.confidence).map(([k, v]) => [k, Math.round(v.moyenne * 100)]))} />
            <p className="ui-field__hint" style={{ marginTop: "var(--sp-2)" }}>Confiance moyenne (%) — auto-déclarée, à interpréter avec prudence.</p>
          </Card>

          <Card title="Latence par moteur (ms / verbatim)">
            <BarList data={m.latency_ms} color="var(--cu-info, #3b82f6)" />
          </Card>

          <Card title="Distribution de sentiment par moteur">
            <StackedSentimentBar data={m.sentiment} />
          </Card>

          <Card title="Win-rate du juge Claude"
                actions={<Badge tone="neutral">mode dégradé</Badge>}>
            <EmptyState title="Juge non disponible"
                        description="Le juge Claude (win-rate sur les divergences) est livré au lot C5." />
          </Card>

          <div>
            <a href={comparisonExportUrl(selected.id)}>
              <Button variant="secondary" size="sm">Exporter le détail (CSV)</Button>
            </a>
          </div>
        </>
      )}
    </div>
  );
}
