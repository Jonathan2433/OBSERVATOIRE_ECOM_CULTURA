import { useRef, useState, type DragEvent } from "react";

export interface FilesDropzoneProps {
  label: string;
  hint?: string;
  accept?: string;
  files: File[];
  onChange: (files: File[]) => void;
  max?: number;
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / 1024 / 1024).toFixed(1)} Mo`;
}

/**
 * Zone de dépôt de PLUSIEURS fichiers.
 *
 * Il n'y a rien à déclarer sur la nature de chaque fichier : la source est
 * identifiée à la lecture, sur le jeu de colonnes. Un mois complet — post-achat
 * et post-réception, ancien et nouveau format, Mopinion desktop et mobile — se
 * dépose en une fois.
 */
export function FilesDropzone({
  label, hint, accept = ".xlsx,.csv", files, onChange, max = 20,
}: FilesDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  // Déduplique sur (nom, taille) : re-déposer le même fichier est une fausse
  // manœuvre courante, et un doublon compterait deux fois dans les volumes.
  const ajouter = (nouveaux: FileList | null) => {
    if (!nouveaux?.length) return;
    const vus = new Set(files.map((f) => `${f.name}:${f.size}`));
    const ajouts = Array.from(nouveaux).filter((f) => !vus.has(`${f.name}:${f.size}`));
    onChange([...files, ...ajouts].slice(0, max));
  };

  const retirer = (i: number) => onChange(files.filter((_, k) => k !== i));

  const cls = ["ui-dropzone", drag ? "is-drag" : "", files.length ? "is-filled" : ""]
    .filter(Boolean).join(" ");
  const total = files.reduce((n, f) => n + f.size, 0);

  return (
    <div className="ui-stack" style={{ gap: "var(--sp-2)" }}>
      <div
        className={cls}
        role="button" tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputRef.current?.click(); }
        }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e: DragEvent) => { e.preventDefault(); setDrag(false); ajouter(e.dataTransfer.files); }}
        aria-label={`${label} — déposer un ou plusieurs fichiers ${accept}`}
      >
        <input ref={inputRef} type="file" accept={accept} multiple hidden
               onChange={(e) => { ajouter(e.target.files); e.target.value = ""; }} />
        <div className="ui-dropzone__label">{label}</div>
        <div className="ui-muted">
          {files.length
            ? `${files.length} fichier${files.length > 1 ? "s" : ""} · ${humanSize(total)} — cliquer pour en ajouter`
            : hint ?? "Glisser-déposer ou cliquer"}
        </div>
      </div>

      {files.length > 0 && (
        <ul className="ui-stack" style={{ gap: 4, listStyle: "none", margin: 0, padding: 0 }}>
          {files.map((f, i) => (
            <li key={`${f.name}:${f.size}`} className="ui-row"
                style={{ gap: 8, justifyContent: "space-between", alignItems: "center" }}>
              <span className="ui-row" style={{ gap: 6, minWidth: 0 }}>
                <span aria-hidden>📄</span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {f.name}
                </span>
                <span className="ui-muted">{humanSize(f.size)}</span>
              </span>
              <button type="button" className="ui-btn ui-btn--ghost ui-btn--sm"
                      onClick={(e) => { e.stopPropagation(); retirer(i); }}
                      aria-label={`Retirer ${f.name}`}>
                Retirer
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
