import { useId } from "react";
import type { AnalysisFilters } from "../api";
import { ANALYSIS_SOURCES } from "../analysisFilters";
import { SOURCE_LABELS } from "../satisfactionDisplay";
import { Button, Card, Chip, Input } from "../ui";

export default function AnalysisFiltersBar({ filters, onChange }: {
  filters: AnalysisFilters;
  onChange: (filters: AnalysisFilters) => void;
}) {
  const sourcesLabelId = useId();
  const periodLabelId = useId();
  const selected = filters.sources ?? [];
  const toggleSource = (source: string) => {
    const sources = selected.includes(source)
      ? selected.filter((item) => item !== source)
      : [...selected, source];
    onChange({ ...filters, sources });
  };
  const activeCount = selected.length + (filters.date_from ? 1 : 0) + (filters.date_to ? 1 : 0);
  const active = activeCount > 0;

  return (
    <Card
      title="Périmètre d’analyse"
      actions={
        <div className="ui-row">
          <span className="analysis-filters__count">
            {active ? `${activeCount} filtre${activeCount > 1 ? "s" : ""} actif${activeCount > 1 ? "s" : ""}` : "Aucun filtre actif"}
          </span>
          <Button size="sm" variant="ghost" onClick={() => onChange({})} disabled={!active}>
            Réinitialiser
          </Button>
        </div>
      }
    >
      <div className="analysis-filters">
        <div className="analysis-filters__group analysis-filters__group--sources">
          <span className="analysis-filters__label" id={sourcesLabelId}>Sources</span>
          <div className="analysis-filters__chips" role="group" aria-labelledby={sourcesLabelId}>
            {ANALYSIS_SOURCES.map((source) => (
              <Chip key={source} active={selected.includes(source)} onClick={() => toggleSource(source)}>
                {SOURCE_LABELS[source] ?? source}
              </Chip>
            ))}
          </div>
        </div>

        <div className="analysis-filters__divider" aria-hidden="true" />

        <div className="analysis-filters__group analysis-filters__group--period">
          <span className="analysis-filters__label" id={periodLabelId}>Période</span>
          <div className="analysis-filters__dates" role="group" aria-labelledby={periodLabelId}>
            <Input label="Publication du" type="date" value={filters.date_from ?? ""}
                   onChange={(event) => onChange({ ...filters, date_from: event.target.value || undefined })} />
            <Input label="Publication au" type="date" value={filters.date_to ?? ""}
                   onChange={(event) => onChange({ ...filters, date_to: event.target.value || undefined })} />
          </div>
          <p className="ui-field__hint">
            Les dates portent sur la publication du retour client, bornes incluses. Une date inconnue n’est jamais remplacée par la date d’upload.
          </p>
        </div>
      </div>
    </Card>
  );
}
