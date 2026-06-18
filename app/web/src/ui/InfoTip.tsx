import type { ReactNode } from "react";

export interface InfoTipProps {
  text: ReactNode;
  label?: string;
}

/** Petite info-bulle contextuelle (ⓘ) affichée au survol / focus clavier. */
export function InfoTip({ text, label }: InfoTipProps) {
  return (
    <span className="ui-infotip" tabIndex={0}
          aria-label={label ?? (typeof text === "string" ? text : "Aide")}>
      <span className="ui-infotip__icon" aria-hidden="true">i</span>
      <span className="ui-infotip__bubble" role="tooltip">{text}</span>
    </span>
  );
}
