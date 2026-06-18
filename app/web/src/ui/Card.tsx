import type { ReactNode } from "react";

export interface CardProps {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Surface de contenu. En-tête (titre + actions) optionnel. */
export function Card({ title, actions, children, className }: CardProps) {
  const cls = ["ui-card", className].filter(Boolean).join(" ");
  return (
    <section className={cls}>
      {(title || actions) && (
        <header className="ui-card__header">
          {title && <h3 className="ui-card__title">{title}</h3>}
          {actions && <div className="ui-spacer" />}
          {actions}
        </header>
      )}
      <div className="ui-card__body">{children}</div>
    </section>
  );
}

export interface StatCardProps {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
}

/** Tuile KPI : chiffre clé + libellé + indice. */
export function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="ui-stat">
      <div className="ui-stat__label">{label}</div>
      <div className="ui-stat__value">{value}</div>
      {hint && <div className="ui-stat__hint">{hint}</div>}
    </div>
  );
}
