import { useEffect, type ReactNode } from "react";

export interface DrawerProps {
  open: boolean;
  title?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

/** Panneau latéral droit (overlay). Ferme sur Échap, clic hors panneau, ou bouton. */
export function Drawer({ open, title, onClose, children }: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="ui-overlay" onClick={onClose} role="presentation">
      <aside className="ui-drawer" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <header className="ui-drawer__header">
          <span className="ui-drawer__title">{title}</span>
          <button className="ui-drawer__close" onClick={onClose} aria-label="Fermer">×</button>
        </header>
        <div className="ui-drawer__body">{children}</div>
      </aside>
    </div>
  );
}
