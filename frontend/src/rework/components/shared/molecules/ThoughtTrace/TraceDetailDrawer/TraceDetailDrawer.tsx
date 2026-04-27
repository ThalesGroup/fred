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

import { lazy, Suspense, useEffect } from "react";
import type { TraceEntry } from "../../../../../utils/traceUtils";
import {
  entryLabel,
  textOf,
  toolArgs,
  toolName,
  toolResultContent,
  toolResultLatencyMs,
  toolResultOk,
  formatLatencyMs,
} from "../../../../../utils/traceUtils";
import styles from "./TraceDetailDrawer.module.css";

const MonacoEditor = lazy(() => import("@monaco-editor/react").then((m) => ({ default: m.Editor })));

interface TraceDetailDrawerProps {
  entry: TraceEntry;
  onClose: () => void;
}

function JsonPane({ value }: { value: unknown }) {
  const json = JSON.stringify(value, null, 2);
  return (
    <Suspense fallback={<pre className={styles.fallback}>{json}</pre>}>
      <MonacoEditor
        height="100%"
        language="json"
        value={json}
        theme="vs-dark"
        options={{
          readOnly: true,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 12,
          lineNumbers: "off",
          folding: true,
        }}
      />
    </Suspense>
  );
}

function drawerPayload(entry: TraceEntry): unknown {
  if (entry.kind === "solo") {
    const msg = entry.message;
    return {
      channel: msg.channel,
      role: msg.role,
      rank: msg.rank,
      text: textOf(msg) || undefined,
      metadata: msg.metadata,
    };
  }
  const callPayload = {
    call_id:
      entry.call.parts?.[0] && "call_id" in entry.call.parts[0]
        ? (entry.call.parts[0] as { call_id: string }).call_id
        : undefined,
    tool: toolName(entry.call),
    args: toolArgs(entry.call),
  };
  if (!entry.result) return { call: callPayload };
  return {
    call: callPayload,
    result: {
      ok: toolResultOk(entry.result),
      latency: formatLatencyMs(toolResultLatencyMs(entry.result)),
      content: toolResultContent(entry.result),
    },
  };
}

export function TraceDetailDrawer({ entry, onClose }: TraceDetailDrawerProps) {
  const label = entryLabel(entry);
  const payload = drawerPayload(entry);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <>
      <div className={styles.overlay} onClick={onClose} aria-hidden="true" />
      <aside className={styles.drawer} role="dialog" aria-modal="true" aria-label={`${label} detail`}>
        <header className={styles.drawerHeader}>
          <span className={styles.drawerTitle}>{label}</span>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className={styles.drawerBody}>
          <JsonPane value={payload} />
        </div>
      </aside>
    </>
  );
}
