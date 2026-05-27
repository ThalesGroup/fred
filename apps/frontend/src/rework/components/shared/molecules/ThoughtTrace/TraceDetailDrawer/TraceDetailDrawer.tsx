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

import { useState } from "react";
import IconButton from "@shared/atoms/IconButton/IconButton";
import MonacoPane from "@shared/atoms/MonacoPane/MonacoPane";
import { InlineDrawer } from "../../InlineDrawer/InlineDrawer";
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

interface TraceDetailDrawerProps {
  entry: TraceEntry;
  onClose: () => void;
}

function tryParseJson(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
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
      content: tryParseJson(toolResultContent(entry.result)),
    },
  };
}

export function TraceDetailDrawer({ entry, onClose }: TraceDetailDrawerProps) {
  const label = entryLabel(entry);
  const payload = drawerPayload(entry);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard
      .writeText(JSON.stringify(payload, null, 2))
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  };

  return (
    <InlineDrawer open={true} onClose={onClose} title={label}>
      <div className={styles.toolbar}>
        <span className={styles.spacer} />
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: copied ? "check_circle" : "content_copy" }}
          aria-label={copied ? "Copied" : "Copy JSON"}
          onClick={handleCopy}
        />
      </div>
      <MonacoPane
        value={JSON.stringify(payload, null, 2)}
        height="calc(100vh - 160px)"
        options={{ lineNumbers: "off", folding: true }}
      />
    </InlineDrawer>
  );
}
