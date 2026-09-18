import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { AnalysisFilters } from "./api";

export const ANALYSIS_SOURCES = [
  "MDTC-postachat",
  "MDTC-postrecep",
  "Mopinion-desktop",
  "Mopinion-mobile",
  // Lots historiques ou schémas non affinés par le chargeur.
  "MDTC",
  "Mopinion",
] as const;

export function useAnalysisFilters() {
  const [params, setParams] = useSearchParams();
  const serialized = params.toString();
  const filters = useMemo<AnalysisFilters>(() => {
    const current = new URLSearchParams(serialized);
    return {
      sources: current.getAll("source"),
      date_from: current.get("date_from") || undefined,
      date_to: current.get("date_to") || undefined,
    };
  }, [serialized]);

  const setFilters = useCallback((next: AnalysisFilters) => {
    setParams((current) => {
      const updated = new URLSearchParams(current);
      updated.delete("source");
      updated.delete("date_from");
      updated.delete("date_to");
      for (const source of next.sources ?? []) updated.append("source", source);
      if (next.date_from) updated.set("date_from", next.date_from);
      if (next.date_to) updated.set("date_to", next.date_to);
      return updated;
    }, { replace: true });
  }, [setParams]);

  return { filters, setFilters };
}
