export interface ProgressBarProps {
  /** Pourcentage 0–100. Si `indeterminate`, ignoré. */
  value?: number;
  indeterminate?: boolean;
  showLabel?: boolean;
}

/** Barre de progression (déterminée ou indéterminée). */
export function ProgressBar({ value = 0, indeterminate = false, showLabel = true }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="ui-progress" role="progressbar"
         aria-valuenow={indeterminate ? undefined : pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="ui-progress__track">
        <div className={"ui-progress__bar" + (indeterminate ? " is-indeterminate" : "")}
             style={indeterminate ? undefined : { width: `${pct}%` }} />
      </div>
      {showLabel && !indeterminate && <span className="ui-progress__label">{pct}%</span>}
    </div>
  );
}
