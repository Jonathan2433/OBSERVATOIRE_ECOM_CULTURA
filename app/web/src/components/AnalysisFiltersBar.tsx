import type { AnalysisFilters } from "../api";
import { ANALYSIS_SOURCES } from "../analysisFilters";
import { SOURCE_LABELS } from "../satisfactionDisplay";
import { Button, Card, Chip, Input } from "../ui";

export default function AnalysisFiltersBar({ filters, onChange }: {
  filters: AnalysisFilters;
  onChange: (filters: AnalysisFilters) => void;
}) {
  const selected = filters.sources ?? [];
  const toggleSource = (source: string) => {
    const sources = selected.includes(source)
      ? selected.filter((item) => item !== source)
      : [...selected, source];
    onChange({ ...filters, sources });
  };
  const active = selected.length > 0 || !!filters.date_from || !!filters.date_to;

  return (
    <Card title="Périmètre d’analyse" actions={active ? (
      <Button size="sm" variant="ghost" onClick={() => onChange({})}>Réinitialiser</Button>
    ) : undefined}>
      <div className="ui-toolbar">
        <span className="ui-muted">Sources</span>
        {ANALYSIS_SOURCES.map((source) => (
          <Chip key={source} active={selected.includes(source)} onClick={() => toggleSource(source)}>
            {SOURCE_LABELS[source] ?? source}
          </Chip>
        ))}
        <span className="ui-toolbar__sep" />
        <Input label="Publication du" type="date" value={filters.date_from ?? ""}
               onChange={(event) => onChange({ ...filters, date_from: event.target.value || undefined })} />
        <Input label="Publication au" type="date" value={filters.date_to ?? ""}
               onChange={(event) => onChange({ ...filters, date_to: event.target.value || undefined })} />
      </div>
      <p className="ui-field__hint" style={{ marginBottom: 0 }}>
        Les dates portent sur la publication du retour client, bornes incluses. Une date inconnue n’est jamais remplacée par la date d’upload.
      </p>
    </Card>
  );
}
