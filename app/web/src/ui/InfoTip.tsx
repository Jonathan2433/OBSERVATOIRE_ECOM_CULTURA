import { useRef, useState, type ReactNode } from "react";

export interface InfoTipProps {
  text: ReactNode;
  label?: string;
}

/** Info-bulle contextuelle (ⓘ) au survol / focus clavier.
 *  La bulle est positionnée en `fixed` pour échapper aux conteneurs qui rognent
 *  (tables à défilement), et bornée pour ne pas déborder de la fenêtre. */
export function InfoTip({ text, label }: InfoTipProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  const open = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const half = 134; // demi-largeur max approximative de la bulle
    const x = Math.min(Math.max(r.left + r.width / 2, half), window.innerWidth - half);
    setPos({ x, y: r.top - 6 });
  };
  const close = () => setPos(null);

  return (
    <span
      ref={ref} className="ui-infotip" tabIndex={0}
      aria-label={label ?? (typeof text === "string" ? text : "Aide")}
      onMouseEnter={open} onMouseLeave={close} onFocus={open} onBlur={close}
    >
      <span className="ui-infotip__icon" aria-hidden="true">i</span>
      {pos && (
        <span className="ui-infotip__bubble" role="tooltip" style={{ left: pos.x, top: pos.y }}>
          {text}
        </span>
      )}
    </span>
  );
}
