"use client";

import { CircleCheckBig, Info, TriangleAlert, X } from "lucide-react";
import { createContext, useCallback, useContext, useState } from "react";

type Tone = "success" | "error" | "info";
type Toast = { id: number; tone: Tone; title: string; body?: string };
type Ctx = (tone: Tone, title: string, body?: string) => void;

const ToastContext = createContext<Ctx>(() => {});
const ICON = { success: CircleCheckBig, error: TriangleAlert, info: Info };

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = (id: number) => setToasts((t) => t.filter((x) => x.id !== id));

  const push = useCallback<Ctx>((tone, title, body) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, tone, title, body }]);
    setTimeout(() => dismiss(id), tone === "error" ? 9000 : 4500);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => {
          const Icon = ICON[t.tone];
          return (
            <div key={t.id} className={`toast ${t.tone}`} role={t.tone === "error" ? "alert" : "status"}>
              <Icon size={18} />
              <div>
                <b>{t.title}</b>
                {t.body && <p>{t.body}</p>}
              </div>
              <button className="icon-btn" onClick={() => dismiss(t.id)} aria-label="Dismiss">
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
