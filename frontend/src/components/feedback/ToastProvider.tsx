import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import { extractApiErrorMessage } from '../../api/client';
import { cn } from '../../lib/cn';

export type ToastTone = 'success' | 'error' | 'info';

export interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  message?: string;
}

interface ToastContextValue {
  toasts: Toast[];
  push: (toast: Omit<Toast, 'id'>) => void;
  /** Convenience: render a toast from any thrown value. */
  pushError: (error: unknown, title?: string) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue>({
  toasts: [],
  push: () => undefined,
  pushError: () => undefined,
  dismiss: () => undefined,
});

let nextId = 1;
const AUTO_DISMISS_MS = 7000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (toast: Omit<Toast, 'id'>) => {
      const id = nextId++;
      setToasts((current) => [...current, { ...toast, id }]);
      window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss],
  );

  const pushError = useCallback(
    (error: unknown, title = 'Request failed') => {
      push({ tone: 'error', title, message: extractApiErrorMessage(error) });
    },
    [push],
  );

  const value = useMemo<ToastContextValue>(
    () => ({ toasts, push, pushError, dismiss }),
    [toasts, push, pushError, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            data-testid="toast"
            data-tone={toast.tone}
            className={cn(
              'pointer-events-auto flex animate-fade-in items-start gap-3 rounded-xl border px-4 py-3 shadow-pop',
              toast.tone === 'error'
                ? 'border-rose-200 bg-white text-rose-900'
                : toast.tone === 'success'
                  ? 'border-emerald-200 bg-white text-emerald-900'
                  : 'border-slate-200 bg-white text-slate-800',
            )}
          >
            <span className="mt-0.5 shrink-0">
              {toast.tone === 'error' ? (
                <AlertTriangle className="h-4 w-4 text-rose-600" aria-hidden="true" />
              ) : toast.tone === 'success' ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
              ) : (
                <Info className="h-4 w-4 text-slate-500" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{toast.title}</p>
              {toast.message ? (
                <p className="mt-0.5 break-words text-xs leading-relaxed opacity-80">
                  {toast.message}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismiss(toast.id)}
              className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  return useContext(ToastContext);
}

export default ToastProvider;