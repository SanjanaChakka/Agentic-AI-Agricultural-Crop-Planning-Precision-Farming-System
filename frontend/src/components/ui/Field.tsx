import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { useId } from 'react';
import { cn } from '../../lib/cn';

const FIELD_CLASS =
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 disabled:bg-slate-50 disabled:text-slate-500';

/**
 * A single labelled control. `children` receives a generated id so the `<label>`
 * is always wired to a real focusable element - accessibility is not optional
 * here. For a *set* of related controls (checkbox groups, radio groups) use
 * `FieldGroup`, which uses fieldset/legend instead.
 */
export function FieldRow({
  label,
  hint,
  error,
  children,
  required,
  className,
}: {
  label: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: (id: string) => ReactNode;
  required?: boolean;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={id} className="label-caps block">
        {label}
        {required ? <span className="ml-0.5 text-rose-600">*</span> : null}
      </label>
      {children(id)}
      {hint ? <p className="text-[11px] leading-snug text-slate-500">{hint}</p> : null}
      {error ? <p className="text-[11px] text-rose-700">{error}</p> : null}
    </div>
  );
}

/** A labelled group of related controls (checkbox / radio clusters). */
export function FieldGroup({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <fieldset className={cn('space-y-1.5', className)}>
      <legend className="label-caps">{label}</legend>
      {children}
      {hint ? <p className="text-[11px] leading-snug text-slate-500">{hint}</p> : null}
    </fieldset>
  );
}

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(FIELD_CLASS, className)} {...rest} />;
}

export function TextArea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(FIELD_CLASS, 'min-h-[72px] resize-y', className)} {...rest} />;
}

export function Select({
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(FIELD_CLASS, 'appearance-none pr-8', className)} {...rest}>
      {children}
    </select>
  );
}

export function Checkbox({
  label,
  hint,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: ReactNode }) {
  const id = useId();
  return (
    <div className={cn('flex items-start gap-2.5', className)}>
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-700 focus:ring-brand-500"
        {...rest}
      />
      <label htmlFor={id} className="text-xs leading-snug text-slate-700">
        {label}
        {hint ? <span className="mt-0.5 block text-[11px] text-slate-500">{hint}</span> : null}
      </label>
    </div>
  );
}

export function FormGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('grid gap-4 sm:grid-cols-2 lg:grid-cols-3', className)}>{children}</div>
  );
}