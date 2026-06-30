import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  comparisonExportUrl, createComparison, getComparison, getVerdicts, listComparisons, listModels,
  type ComparisonRun, type JudgeVerdict, type ModelVersion,
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
  const [judge, setJudge] = useState(false);
  const [verdicts, setVerdicts] = useState<JudgeVerdict[]>([]);
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

  // Charge les verdicts du juge quand un run terminé avec juge est sélectionné.
  useEffect(() => {
    if (selected?.status === "done" && selected.metrics?.judge) {
      getVerdicts(selected.id, 0, 20).then((p) => setVerdicts(p.items)).catch(() => setVerdicts([]));
    } else {
      setVerdicts([]);
    }
  }, [selected]);

  const toggleEngine = (label: string) =>
    setEngines((prev) => (prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label]));

  const launch = async () => {
    setError(null);
    if (engines.length < 2) { setError("Sélectionnez au moins 2 moteurs."); return; }
    if (engines.length > 3) { setError("3 moteurs maximum."); return; }
    setBusy(true);
    try {
      const run = await createComparison(batchId, {
        engines, sample_size: sample, seed, judge_enabled: judge && claudeAvailable,
      });
      setRuns((prev) => [run, ...prev]);
      setSelected(run);
    } catch (e: any) {
      setError(e?.message ?? "Erreur au lancement");
    } finally {
      setBusy(false);
    }
  };

  const m = selected?.metrics ?? null;
  const pct = (v: number) => Math.round(v * 100);

  return (
    <div className="ui-stack">
      <Card title="Lancer une comparaison"
            actions={!isAdmin ? <Badge tone="neutral">lecture seule (admin requis)</Badge> : undefined}>
        <p className="ui-muted" style={{ marginBottom: "var(--sp-3)" }}>
          Rejoue un échantillon de ce lot à travers 2-3 moteurs et mesure leurs écarts.
          Le replay ne porte que sur le texte déjà anonymisé. Activez le <b>juge Claude</b>
          {" "}pour faire trancher les désaccords (win-rate) — si une clé Claude est configurée.
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
          <label className="ui-row" style={{ gap: 6, cursor: isAdmin && claudeAvailable ? "pointer" : "default" }}>
            <input type="checkbox" checked={judge && claudeAvailable} disabled={!isAdmin || !claudeAvailable}
                   onChange={(e) => setJudge(e.target.checked)} />
            <span>Juge Claude {!claudeAvailable && <span className="ui-muted">(clé absente)</span>}</span>
          </label>
          <Button variant="primary" loading={busy} disabled={!isAdmin || engines.length < 2} onClick={launch}>
            {busy ? "Lancement…" : "Comparer"}
          </Button>
        </div>
        {judge && claudeAvailable && (
          <p className="ui-field__hint" style={{ marginTop: "var(--sp-2)" }}>
            ⚠️ Le juge envoie les verbatims divergents (anonymisés) à l'API Anthropic — consomme du crédit.
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
                #{r.id} · {r.engine_labels.length} moteurs · n={r.sample_size}{r.judge_enabled ? " · juge" : ""} · {r.status}
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
            <StatCard label="Verbatims comparés" value={m.sample_size} />
            <StatCard label="Moteurs" value={m.engines.length} />
            <StatCard label="Désaccords" value={m.n_divergences}
                      hint={`sur ${m.sample_size} — grand thème (niv.1) différent entre moteurs`} />
          </div>

          <Card title="Accord entre moteurs sur le grand thème (niv.1)">
            <BarList max={100} suffix=" %"
                     data={Object.fromEntries(Object.entries(m.agreement).map(([k, v]) => [k, pct(v)]))} />
            <p className="ui-field__hint" style={{ marginTop: "var(--sp-2)" }}>
              Part des verbatims où les deux moteurs choisissent le <b>même grand thème</b>. 100 % = classifications
              identiques au niveau 1 ; bas = visions très différentes. (Ne dit pas qui a raison — voir le juge.)
            </p>
          </Card>

          <Card title="Assurance moyenne des moteurs (auto-déclarée)">
            <BarList max={100} suffix=" %"
                     data={Object.fromEntries(Object.entries(m.confidence).map(([k, v]) => [k, pct(v.moyenne)]))} />
            <p className="ui-field__hint" style={{ marginTop: "var(--sp-2)" }}>
              Score de confiance que <b>chaque moteur s'attribue à lui-même</b> (0–100 %). ⚠️ C'est son niveau
              d'assurance, <b>pas sa justesse</b> : un moteur peut être très sûr et se tromper.
            </p>
          </Card>

          <Card title="Vitesse de traitement par moteur">
            <BarList data={Object.fromEntries(Object.entries(m.latency_ms).map(([k, v]) => [k, Math.round(v)]))}
                     suffix=" ms" color="var(--cu-info, #3b82f6)" />
            <p className="ui-field__hint" style={{ marginTop: "var(--sp-2)" }}>
              Temps moyen par verbatim (millisecondes). <b>Plus bas = plus rapide.</b>
            </p>
          </Card>

          <Card title="Répartition des sentiments par moteur">
            <StackedSentimentBar data={m.sentiment} />
            <p className="ui-field__hint" style={{ marginTop: "var(--sp-2)" }}>
              Combien de verbatims chaque moteur juge Négatif / Neutre / Positif sur l'échantillon.
            </p>
          </Card>

          {m.judge ? (
            <>
              <Card title="Qui gagne les désaccords ? — verdict du juge Claude"
                    actions={<Badge tone="info">{m.judge.n_judged} duels jugés</Badge>}>
                <BarList max={100} suffix=" %" color="var(--cu-success, #16a34a)"
                         data={Object.fromEntries(Object.entries(m.judge.win_rate).map(([k, v]) => [k, pct(v)]))} />
                <p className="ui-field__hint" style={{ marginTop: "var(--sp-2)" }}>
                  Sur les verbatims où les moteurs divergent, Claude (aveuglé : il ne connaît pas les noms des moteurs)
                  désigne la classification la plus pertinente. <b>Win-rate</b> = % de duels gagnés. {m.judge.n_ties} nul(s).
                </p>
              </Card>

              {verdicts.length > 0 && (
                <Card title="Exemples de désaccords arbitrés">
                  <div className="ui-stack" style={{ gap: "var(--sp-3)" }}>
                    {verdicts.map((v) => (
                      <div key={v.id} style={{ borderLeft: "3px solid var(--cu-neutral-300)", paddingLeft: "var(--sp-3)" }}>
                        {v.verbatim && <p style={{ margin: 0 }}>« {v.verbatim} »</p>}
                        <p className="ui-muted" style={{ margin: "4px 0", fontSize: "var(--fs-sm)" }}>
                          {v.engine_a} : <b>{v.classif_a || "—"}</b> &nbsp;vs&nbsp; {v.engine_b} : <b>{v.classif_b || "—"}</b>
                        </p>
                        <p style={{ margin: "4px 0", fontSize: "var(--fs-sm)" }}>
                          <Badge tone={v.winner === "tie" ? "neutral" : "success"}>
                            {v.winner === "tie" ? "égalité" : `gagnant : ${v.winner === "a" ? v.engine_a : v.engine_b}`}
                          </Badge>{" "}
                          {v.rationale && <span className="ui-muted">{v.rationale}</span>}
                        </p>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          ) : (
            <Card title="Qui gagne les désaccords ? — juge Claude"
                  actions={<Badge tone="neutral">mode dégradé</Badge>}>
              <EmptyState title="Juge non exécuté"
                          description={claudeAvailable
                            ? "Relancez une comparaison en cochant « Juge Claude » pour arbitrer les désaccords."
                            : "Aucune clé Claude configurée : la comparaison reste objective (accord/confiance/latence), sans arbitrage."} />
            </Card>
          )}

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
