import { useId } from "react";
import type {
  InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes, ReactNode,
} from "react";

interface FieldBase {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
}

function Wrapper({
  label, hint, error, id, children,
}: FieldBase & { id: string; children: ReactNode }) {
  return (
    <div className="ui-field">
      {label && <label className="ui-field__label" htmlFor={id}>{label}</label>}
      {children}
      {hint && !error && <span className="ui-field__hint">{hint}</span>}
      {error && <span className="ui-field__error">{error}</span>}
    </div>
  );
}

export type InputProps = InputHTMLAttributes<HTMLInputElement> & FieldBase;
export function Input({ label, hint, error, id, className, ...rest }: InputProps) {
  const auto = useId();
  const fid = id ?? auto;
  const cls = ["ui-input", error ? "ui-input--invalid" : "", className].filter(Boolean).join(" ");
  return (
    <Wrapper label={label} hint={hint} error={error} id={fid}>
      <input id={fid} className={cls} aria-invalid={error ? true : undefined} {...rest} />
    </Wrapper>
  );
}

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & FieldBase;
export function Select({ label, hint, error, id, className, children, ...rest }: SelectProps) {
  const auto = useId();
  const fid = id ?? auto;
  const cls = ["ui-select", error ? "ui-select--invalid" : "", className].filter(Boolean).join(" ");
  return (
    <Wrapper label={label} hint={hint} error={error} id={fid}>
      <select id={fid} className={cls} aria-invalid={error ? true : undefined} {...rest}>{children}</select>
    </Wrapper>
  );
}

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & FieldBase;
export function Textarea({ label, hint, error, id, className, ...rest }: TextareaProps) {
  const auto = useId();
  const fid = id ?? auto;
  const cls = ["ui-textarea", error ? "ui-textarea--invalid" : "", className].filter(Boolean).join(" ");
  return (
    <Wrapper label={label} hint={hint} error={error} id={fid}>
      <textarea id={fid} className={cls} aria-invalid={error ? true : undefined} {...rest} />
    </Wrapper>
  );
}
