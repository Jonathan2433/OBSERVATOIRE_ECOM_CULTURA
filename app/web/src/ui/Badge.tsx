import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "primary" | "success" | "warning" | "danger" | "info";

export interface BadgeProps {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
}

/** Étiquette de statut / catégorie, mappée sur les couleurs sémantiques. */
export function Badge({ tone = "neutral", dot = false, children }: BadgeProps) {
  return (
    <span className={`ui-badge ui-badge--${tone}`}>
      {dot && <span className="ui-badge__dot" aria-hidden="true" />}
      {children}
    </span>
  );
}
