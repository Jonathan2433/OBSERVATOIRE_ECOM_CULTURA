import type { SatisfactionKpi } from "../api";
import { Badge, Card, InfoTip, StatCard } from "../ui";
import BarList from "./BarList";

/** Notes de l'échelle commune, dans l'ORDRE de l'échelle et non du volume. */
const NOTES = ["1", "2", "3", "4"];
const LIBELLES: Record<string, string> = {
  "1": "1 — pas du tout satisfait",
  "2": "2 — plutôt pas satisfait",
  "3": "3 — plutôt satisfait",
  "4": "4 — très satisfait",
};

const pct = (v: number | null | undefined) =>
  v == null ? "non renseigné" : `${(v * 100).toFixed(1)} %`;

/**
 * Satisfaction DÉCLARÉE par les clients d'un périmètre (un lot, ou tous).
 *
 * Ce panneau répond à la question que le seul compteur d'« insatisfaction forte »
 * laissait sans réponse : combien de clients sont satisfaits. Le signal
 * d'insatisfaction est une déduction du modèle sur le texte ; la note, elle, est
 * ce que le client a coché. Les deux sont affichés côte à côte sans être mêlés.
 *
 * Trois précautions de lecture sont portées par le composant lui-même :
 *
 * * une moyenne sur zéro note s'affiche « non renseigné », jamais 0 ;
 * * les verbatims sans note sont comptés à part, pour qu'un taux calculé sur un
 *   dixième du lot ne se lise pas comme un taux sur le lot entier ;
 * * la conversion des échelles sources vers 1-4 est une hypothèse eXalt tant que
 *   Cultura ne l'a pas validée (Q-17) — le bandeau le dit, parce qu'un taux de
 *   satisfaction est exactement le chiffre qui circule sans son avertissement.
 */
export default function SatisfactionPanel({ sat, titre = "Satisfaction client déclarée" }: {
  sat: SatisfactionKpi;
  titre?: string;
}) {
  const couverture = sat.n_notes + sat.n_sans_note;
  const distribution = Object.fromEntries(
    NOTES.map((n) => [LIBELLES[n], sat.distribution[n] ?? 0]));
  const horsEchelle = Object.entries(sat.distribution)
    .filter(([n]) => !NOTES.includes(n));

  return (
    <Card title={titre} actions={
      sat.sources_hypothese.length > 0 ? (
        <span className="ui-row" style={{ gap: 4 }}>
          <Badge tone="warning">conversion à valider</Badge>
          <InfoTip text={`La mise à l'échelle commune 1-4 de ${sat.sources_hypothese.join(", ")} est une hypothèse eXalt : Cultura n'a pas fourni de table officielle (Q-17). Les comparaisons de niveau ENTRE sources reposent donc sur cette hypothèse ; les volumes, eux, ne sont pas concernés.`} />
        </span>
      ) : undefined
    }>
      <div className="ui-stack">
        {sat.n_notes === 0 ? (
          <p className="ui-muted">
            Aucune note conservée sur ce périmètre. Les lots traités avant la mise en
            place de cet indicateur n'en portent pas : relancer un traitement les fera
            apparaître. Une note absente n'est pas un zéro — rien n'est déduit ici.
          </p>
        ) : (
          <>
            <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
              <StatCard label="Note moyenne"
                        value={sat.moyenne != null ? `${sat.moyenne.toFixed(2)} / ${sat.echelle.max}` : "non renseigné"}
                        hint={`sur ${sat.n_notes} note(s)`} />
              <StatCard label="Clients satisfaits" value={pct(sat.taux_satisfaction)}
                        hint={`${sat.n_satisfaits} note(s) ≥ ${sat.echelle.seuil_satisfait}`} />
              <StatCard label="Clients insatisfaits"
                        value={sat.n_notes ? pct(sat.n_insatisfaits / sat.n_notes) : "non renseigné"}
                        hint={`${sat.n_insatisfaits} note(s) < ${sat.echelle.seuil_satisfait}`} />
              <StatCard label="Sans note" value={sat.n_sans_note}
                        hint={couverture ? `${((sat.n_notes / couverture) * 100).toFixed(0)} % du périmètre noté` : undefined} />
            </div>

            <BarList data={distribution} order={NOTES.map((n) => LIBELLES[n])} />

            {horsEchelle.length > 0 && (
              <p className="ui-field__error">
                {sat.hors_echelle} note(s) hors de l'échelle 1-{sat.echelle.max} :{" "}
                {horsEchelle.map(([n, v]) => `${n} (${v})`).join(", ")}. Donnée source non
                conforme — à signaler plutôt qu'à rabattre sur la borne la plus proche.
              </p>
            )}

            {Object.keys(sat.par_source).length > 1 && (
              <div className="ui-table-wrap">
                <table className="ui-table">
                  <thead>
                    <tr><th>Source</th><th>Notes</th><th>Moyenne</th><th>Satisfaits</th></tr>
                  </thead>
                  <tbody>
                    {Object.entries(sat.par_source).map(([source, s]) => (
                      <tr key={source}>
                        <td>{source}</td>
                        <td className="ui-table__num">{s.n_notes}</td>
                        <td className="ui-table__num">{s.moyenne != null ? s.moyenne.toFixed(2) : "—"}</td>
                        <td className="ui-table__num">{pct(s.taux_satisfaction)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
