export interface DashboardSourceGroup {
  key: string;
  title: string;
  sources: string[];
}

/** Ordre métier commun aux cartes Satisfaction et Classifications. */
export const DASHBOARD_SOURCE_GROUPS: DashboardSourceGroup[] = [
  {
    key: "mopinion",
    title: "Mopinion",
    sources: ["Mopinion-mobile", "Mopinion-desktop"],
  },
  {
    key: "mdtc-postachat",
    title: "MDTC — Post-achat web",
    sources: ["MDTC-postachat"],
  },
  {
    key: "mdtc-postrecep",
    title: "MDTC — Post-réception web",
    sources: ["MDTC-postrecep"],
  },
];
