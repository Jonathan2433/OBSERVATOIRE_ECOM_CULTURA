import type { ReactNode } from "react";

export interface ChipProps {
  active?: boolean;
  onClick?: () => void;
  children: ReactNode;
}

/** Filtre activable (bascule on/off). */
export function Chip({ active = false, onClick, children }: ChipProps) {
  return (
    <button type="button" className={"ui-chip" + (active ? " is-on" : "")}
            aria-pressed={active} onClick={onClick}>
      {children}
    </button>
  );
}
