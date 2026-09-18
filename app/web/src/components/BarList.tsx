import type { ReactNode } from "react";

/** Petit graphe en barres horizontales (sans dépendance, piloté par les tokens).
 *  `max` : échelle fixe (ex. 100 pour des pourcentages) ; par défaut, normalisé sur
 *  la plus grande valeur. `suffix` : unité affichée après la valeur (ex. " %").
 *  `order` : force l'ordre des libellés au lieu du tri par volume, et affiche à
 *  zéro ceux qui manquent. Indispensable pour une échelle ORDINALE — une note de
 *  satisfaction se lit 1, 2, 3, 4, jamais du plus fréquent au moins fréquent, et
 *  une note que personne n'a donnée doit rester visible.
 *  `onSelect` transforme chaque ligne en contrôle accessible ; ce mode est utilisé
 *  par la répartition hiérarchique N1 → N2 et reste optionnel pour les autres
 *  graphiques. */
export default function BarList({
  data, color = "var(--cu-primary-500)", max, suffix = "", order,
  selectedKey, onSelect, ariaLabel,
}: {
  data: Record<string, number>;
  color?: string;
  max?: number;
  suffix?: string;
  order?: string[];
  selectedKey?: string | null;
  onSelect?: (key: string) => void;
  ariaLabel?: string;
}) {
  const entries = order
    ? order.map((k) => [k, data[k] ?? 0] as [string, number])
    : Object.entries(data).sort((a, b) => b[1] - a[1]);
  // Un axe ordinal entièrement à zéro n'est pas un graphe à afficher : c'est une
  // absence de mesure, et quatre barres vides se liraient comme quatre vrais zéros.
  if (entries.length === 0 || entries.every(([, v]) => !v)) return <p className="ui-muted">Aucune donnée.</p>;
  const top = max ?? Math.max(...entries.map(([, v]) => v), 1);

  const rowContent = (label: string, value: number): ReactNode => (
    <>
      <span className="bar-list__label" title={label}>{label}</span>
      <span className="bar-list__track" aria-hidden="true">
        <span className="bar-list__fill" style={{ width: `${Math.min(100, (value / top) * 100)}%`, background: color }} />
      </span>
      <span className="bar-list__value">{value}{suffix}</span>
    </>
  );

  return (
    <div className="bar-list" role={onSelect ? "group" : undefined}
         aria-label={onSelect ? ariaLabel : undefined}>
      {entries.map(([label, value]) => onSelect ? (
        <button key={label} type="button"
                className={`bar-list__row bar-list__row--selectable${selectedKey === label ? " is-selected" : ""}`}
                aria-pressed={selectedKey === label}
                onClick={() => onSelect(label)}>
          {rowContent(label, value)}
        </button>
      ) : (
        <div key={label} className="bar-list__row">
          {rowContent(label, value)}
        </div>
      ))}
    </div>
  );
}
