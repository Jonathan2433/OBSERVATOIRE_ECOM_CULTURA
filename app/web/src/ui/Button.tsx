import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children?: ReactNode;
}

/** Bouton du design system. Variante `secondary` par défaut. */
export function Button({
  variant = "secondary", size = "md", loading = false,
  disabled, className, children, ...rest
}: ButtonProps) {
  const cls = ["ui-btn", `ui-btn--${variant}`, `ui-btn--${size}`, className].filter(Boolean).join(" ");
  return (
    <button className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <span className="ui-spinner ui-spinner--sm" aria-hidden="true" />}
      {children}
    </button>
  );
}
