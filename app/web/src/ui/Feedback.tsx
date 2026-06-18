import type { ReactNode } from "react";

export interface SpinnerProps {
  size?: "sm" | "md";
  label?: string;
}

/** Indicateur de chargement. */
export function Spinner({ size = "md", label }: SpinnerProps) {
  return (
    <span className="ui-row" role="status" aria-live="polite">
      <span className={`ui-spinner ui-spinner--${size}`} aria-hidden="true" />
      {label && <span className="ui-muted">{label}</span>}
    </span>
  );
}

export interface EmptyStateProps {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}

/** État vide : message + action suggérée. */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="ui-empty">
      <div className="ui-empty__title">{title}</div>
      {description && <p className="ui-muted">{description}</p>}
      {action}
    </div>
  );
}
