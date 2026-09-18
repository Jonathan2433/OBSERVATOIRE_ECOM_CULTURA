export type SentimentCounts = Record<string, number>;

export const totalSentimentCount = (sentiments: SentimentCounts) =>
  Object.values(sentiments).reduce((total, count) => total + count, 0);

/**
 * Classe les thèmes pour faire remonter en premier les principaux irritants.
 * Les critères secondaires garantissent un ordre stable et compréhensible.
 */
export function sortThemeSentimentRows(data: Record<string, SentimentCounts>) {
  return Object.entries(data).sort(([themeA, sentimentsA], [themeB, sentimentsB]) => {
    const negativeDelta = (sentimentsB["Négatif"] ?? 0) - (sentimentsA["Négatif"] ?? 0);
    if (negativeDelta !== 0) return negativeDelta;

    const totalDelta = totalSentimentCount(sentimentsB) - totalSentimentCount(sentimentsA);
    if (totalDelta !== 0) return totalDelta;

    return themeA.localeCompare(themeB, "fr", { sensitivity: "base" });
  });
}
