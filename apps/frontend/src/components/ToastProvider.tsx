// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import React, { createContext, useCallback, useContext, useState } from "react";
import { Toast, ToastContainer } from "../rework/components/shared/molecules/Toast/Toast";
import type { ToastData, ToastSeverity } from "../rework/components/shared/molecules/Toast/Toast";

// ── Public API ────────────────────────────────────────────────────────────────

export interface ToastInput {
  summary: string;
  detail?: string;
  /** Auto-dismiss ms. null = manual dismiss only. Defaults: success/info/warn=6000, error=null */
  duration?: number | null;
}

interface ToastContextValue {
  showSuccess: (msg: ToastInput) => void;
  showError: (msg: ToastInput) => void;
  showInfo: (msg: ToastInput) => void;
  showWarn: (msg: ToastInput) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

// ── Internal state ────────────────────────────────────────────────────────────

interface ToastState extends ToastData {
  exiting: boolean;
}

// ── Provider ──────────────────────────────────────────────────────────────────

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastState[]>([]);

  const push = useCallback((severity: ToastSeverity, input: ToastInput, defaultDuration: number | null) => {
    const duration = input.duration !== undefined ? input.duration : defaultDuration;
    setToasts((prev) => [
      ...prev,
      { id: Date.now(), severity, summary: input.summary, detail: input.detail, duration, exiting: false },
    ]);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, exiting: true } : t)));
  }, []);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showSuccess = useCallback((msg: ToastInput) => push("success", msg, 6000), [push]);
  const showError = useCallback((msg: ToastInput) => push("error", msg, null), [push]);
  const showInfo = useCallback((msg: ToastInput) => push("info", msg, 6000), [push]);
  const showWarn = useCallback((msg: ToastInput) => push("warning", msg, 6000), [push]);

  return (
    <ToastContext.Provider value={{ showSuccess, showError, showInfo, showWarn }}>
      {children}
      <ToastContainer>
        {toasts.map((toast) => (
          <Toast key={toast.id} {...toast} onClose={dismiss} onExited={remove} />
        ))}
      </ToastContainer>
    </ToastContext.Provider>
  );
};

// ── Hook ──────────────────────────────────────────────────────────────────────

export const useToast = (): ToastContextValue => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
};
