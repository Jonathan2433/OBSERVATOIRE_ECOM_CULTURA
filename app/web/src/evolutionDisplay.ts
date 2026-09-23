export type EvolutionOutcome =
  | { kind: "value"; percent: number }
  | { kind: "new" }
  | { kind: "stable" }
  | { kind: "not-comparable" };

/**
 * Évolution RELATIVE en % — (actuel − référence) / référence — jamais en points.
 * Une référence à 0 rend le % mathématiquement indéfini (division par zéro) :
 * on distingue explicitement "nouveau" (apparition) de "stable" (déjà nul des
 * deux côtés) plutôt que d'afficher un nombre trompeur.
 */
export function relativeEvolution(
  current: number,
  reference: number | null | undefined,
  comparable = true,
): EvolutionOutcome {
  if (!comparable || reference == null) return { kind: "not-comparable" };
  if (reference === 0) return current === 0 ? { kind: "stable" } : { kind: "new" };
  return { kind: "value", percent: ((current - reference) / reference) * 100 };
}

/** Formatage par défaut (décimale ".", ex. "+18.2 %") pour les taux et parts. */
export function formatEvolutionPercent(outcome: EvolutionOutcome, decimals = 1): string {
  switch (outcome.kind) {
    case "not-comparable": return "non comparable";
    case "new": return "nouveau";
    case "stable": return "stable";
    case "value": {
      const sign = outcome.percent > 0 ? "+" : "";
      return `${sign}${outcome.percent.toFixed(decimals)} %`;
    }
  }
}
