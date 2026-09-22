import { formatEvolutionPercent, relativeEvolution, type EvolutionOutcome } from "./evolutionDisplay";

export const SATISFACTION_DISPLAY_MAX = 10;

/**
 * Projette une note NATIVE sur 10. L'API calcule les moyennes avec la même
 * formule; cette fonction centralise seulement l'affichage d'une note unitaire.
 */
export function satisfactionOnTen(value: number, nativeMax: number): number {
  if (!Number.isFinite(nativeMax) || nativeMax <= 0) return value;
  return value * SATISFACTION_DISPLAY_MAX / nativeMax;
}

export const SOURCE_LABELS: Record<string, string> = {
  "MDTC-postachat": "MDTC — Post-achat web",
  "MDTC-postrecep": "MDTC — Post-réception web",
  "Mopinion-desktop": "Mopinion — Ordinateur",
  "Mopinion-mobile": "Mopinion — Mobile",
  MDTC: "MDTC — historique / non précisé",
  Mopinion: "Mopinion — historique / non précisé",
};

export const SOURCE_SHORT_LABELS: Record<string, string> = {
  "MDTC-postachat": "Satisfaction générale",
  "MDTC-postrecep": "Satisfaction générale",
  "Mopinion-desktop": "Ordinateur",
  "Mopinion-mobile": "Mobile",
};

export const CLIENT_STATUS_LABELS = {
  ancien: "Ancien",
  nouveau: "Nouveau",
  non_renseigne: "Statut client non disponible",
} as const;

export function formatOnTen(value: number | null): string {
  return value == null ? "—" : `${value.toFixed(2)} / 10`;
}

/** Format de synthèse : une décimale suffit pour comparer rapidement les cartes. */
export function formatCompactOnTen(value: number | null): string {
  return value == null ? "—" : `${value.toFixed(1).replace(".", ",")} / 10`;
}

/** Évolution RELATIVE (%) d'une note /10, pas un delta en points. */
export function satisfactionEvolution(
  currentOnTen: number | null,
  referenceOnTen: number | null,
  comparable: boolean,
): EvolutionOutcome {
  if (currentOnTen == null) return { kind: "not-comparable" };
  return relativeEvolution(currentOnTen, referenceOnTen, comparable);
}

export function formatSatisfactionEvolution(outcome: EvolutionOutcome): string {
  if (outcome.kind !== "value") return formatEvolutionPercent(outcome);
  const sign = outcome.percent > 0 ? "+" : "";
  return `${sign}${outcome.percent.toFixed(1).replace(".", ",")} %`;
}

export function formatPeriod(start: string | null, end: string | null): string {
  if (!start || !end) return "période indisponible";
  const format = (value: string) => new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
  return start === end ? format(start) : `${format(start)} – ${format(end)}`;
}
