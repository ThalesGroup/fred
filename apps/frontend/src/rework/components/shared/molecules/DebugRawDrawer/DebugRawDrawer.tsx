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
import { InlineDrawer } from "../InlineDrawer/InlineDrawer";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import IconButton from "@shared/atoms/IconButton/IconButton";
import type { ChatMessage } from "../../../../../slices/agentic/agenticOpenApi";
import styles from "./DebugRawDrawer.module.css";

interface DebugRawDrawerProps {
  open: boolean;
  onClose: () => void;
  messages: ChatMessage[];
}

export function DebugRawDrawer({ open, onClose, messages }: DebugRawDrawerProps) {
  const [scopeIndex, setScopeIndex] = useState(0);
  const [copied, setCopied] = useState(false);

  // Last exchange = the exchange_id that appears latest in the message list.
  const lastExchangeId = messages.reduce<string | null>(
    (last, m) => (last === null ? m.exchange_id : m.exchange_id),
    null,
  );

  const displayed = scopeIndex === 0 ? messages.filter((m) => m.exchange_id === lastExchangeId) : messages;
  const json = JSON.stringify(displayed, null, 2);

  const handleCopy = () => {
    navigator.clipboard
      .writeText(json)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  };

  return (
    <InlineDrawer open={open} onClose={onClose} title="Debug — raw messages" width="560px">
      <div className={styles.toolbar}>
        <ButtonGroup
          size="small"
          color="primary"
          selectedIndex={scopeIndex}
          onSelectedIndexChange={setScopeIndex}
          items={[{ label: "Last exchange" }, { label: "All" }]}
        />
        <span className={styles.spacer} />
        <span className={styles.count}>{displayed.length} msg</span>
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: copied ? "check_circle" : "content_copy" }}
          aria-label={copied ? "Copied" : "Copy JSON"}
          onClick={handleCopy}
        />
      </div>
      <pre className={styles.json}>{json}</pre>
    </InlineDrawer>
  );
}
