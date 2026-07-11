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

// The demo capability's side panel (RFC §9 item 3) — the known-good tracer
// proving a capability panel mounts in the reserved right column AND calls the
// capability's OWN auto-mounted route through its OWN generated RTK slice.
//
// Import boundary: the generated hook (`usePostAnalyzeMutation`) is imported
// ONLY here, inside the capability's folder (RFC §9.1).

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import type { CapabilitySidePanelProps } from "../types";
import { useAnalyzeAnalyzePostMutation } from "./api/demoEchoCapabilityOpenApi";
import styles from "./DemoNotesPanel.module.css";

export function DemoNotesPanel({ capabilityId }: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [analyze, { data, isLoading, isError }] = useAnalyzeAnalyzePostMutation();

  return (
    <div className={styles.panel}>
      <p className={styles.hint}>{t(`capability.${capabilityId}.panel.demo_notes.hint`, { defaultValue: "" })}</p>
      <div className={styles.row}>
        <TextInput value={text} onChange={(e) => setText(e.target.value)} placeholder="text" />
        <Button
          color="primary"
          variant="filled"
          size="small"
          disabled={isLoading || text.length === 0}
          onClick={() => {
            void analyze({ demoAnalyzeRequest: { text } });
          }}
        >
          {t(`capability.${capabilityId}.panel.demo_notes.analyze`, { defaultValue: "Analyze" })}
        </Button>
      </div>
      {isError && (
        <p className={styles.error}>
          {t("capability.demo_echo.panel.demo_notes.error", { defaultValue: "Request failed" })}
        </p>
      )}
      {data && (
        <dl className={styles.result}>
          <div className={styles.resultRow}>
            <dt>original</dt>
            <dd>{data.original}</dd>
          </div>
          <div className={styles.resultRow}>
            <dt>transformed</dt>
            <dd>{data.transformed}</dd>
          </div>
          <div className={styles.resultRow}>
            <dt>length</dt>
            <dd>{data.length}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}
