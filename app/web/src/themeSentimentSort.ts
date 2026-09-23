export type SentimentCounts = Record<string, number>;
export type ThemeRankingCriterion = "volume" | "Négatif" | "Neutre" | "Positif";

export const totalSentimentCount = (sentiments: SentimentCounts) =>
  Object.values(sentiments).reduce((total, count) => total + count, 0);

/** Classe les thèmes selon le critère métier actif, avec un ordre stable. */
export function rankThemeLabels(
  volumes: Record<string, number>,
  sentiments: Record<string, SentimentCounts>,
  criterion: ThemeRankingCriterion,
) {
  return Object.keys(volumes).sort((themeA, themeB) => {
    const valueA = criterion === "volume"
      ? volumes[themeA] ?? 0
      : sentiments[themeA]?.[criterion] ?? 0;
    const valueB = criterion === "volume"
      ? volumes[themeB] ?? 0
      : sentiments[themeB]?.[criterion] ?? 0;
    const criterionDelta = valueB - valueA;
    if (criterionDelta !== 0) return criterionDelta;

    if (criterion !== "volume") {
      const totalDelta = (volumes[themeB] ?? 0) - (volumes[themeA] ?? 0);
      if (totalDelta !== 0) return totalDelta;
    }

    return themeA.localeCompare(themeB, "fr", { sensitivity: "base" });
  });
}

export function valuesForThemeCriterion(
  volumes: Record<string, number>,
  sentiments: Record<string, SentimentCounts>,
  criterion: ThemeRankingCriterion,
) {
  if (criterion === "volume") return volumes;
  return Object.fromEntries(
    Object.keys(volumes).map((theme) => [theme, sentiments[theme]?.[criterion] ?? 0]),
  );
}

export function sortThemeSentimentRows(
  data: Record<string, SentimentCounts>,
  criterion: Exclude<ThemeRankingCriterion, "volume"> = "Négatif",
) {
  const volumes = Object.fromEntries(
    Object.entries(data).map(([theme, sentiments]) => [theme, totalSentimentCount(sentiments)]),
  );
  const labels = rankThemeLabels(volumes, data, criterion);
  return labels.map((label) => [label, data[label]] as [string, SentimentCounts]);
}
