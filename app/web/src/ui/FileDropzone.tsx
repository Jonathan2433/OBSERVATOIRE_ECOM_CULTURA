import { useRef, useState, type DragEvent } from "react";

export interface FileDropzoneProps {
  label: string;
  hint?: string;
  accept?: string;
  file: File | null;
  onSelect: (file: File | null) => void;
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / 1024 / 1024).toFixed(1)} Mo`;
}

/** Zone de dépôt d'un fichier (glisser-déposer + clic), avec aperçu nom/taille. */
export function FileDropzone({ label, hint, accept = ".xlsx", file, onSelect }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0] ?? null;
    if (f) onSelect(f);
  };

  const cls = ["ui-dropzone", drag ? "is-drag" : "", file ? "is-filled" : ""].filter(Boolean).join(" ");

  return (
    <div
      className={cls}
      role="button" tabIndex={0}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputRef.current?.click(); } }}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
      aria-label={`${label} — déposer un fichier ${accept}`}
    >
      <input ref={inputRef} type="file" accept={accept} hidden
             onChange={(e) => onSelect(e.target.files?.[0] ?? null)} />
      {file ? (
        <>
          <div className="ui-dropzone__file">
            <span>📄</span>
            <strong>{file.name}</strong>
            <span className="ui-muted">· {humanSize(file.size)}</span>
          </div>
          <button type="button" className="ui-btn ui-btn--ghost ui-btn--sm"
                  onClick={(e) => { e.stopPropagation(); onSelect(null); if (inputRef.current) inputRef.current.value = ""; }}>
            Retirer
          </button>
        </>
      ) : (
        <>
          <div className="ui-dropzone__title">{label}</div>
          <div className="ui-dropzone__hint">{hint ?? `Glisser-déposer ou cliquer (${accept})`}</div>
        </>
      )}
    </div>
  );
}
