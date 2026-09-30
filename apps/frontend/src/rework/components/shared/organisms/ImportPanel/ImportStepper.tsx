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

// Where a file has got to, as the four phases it actually goes through, each
// named in full.
//
// Not a progress bar: no phase reports a fraction of itself, so a bar either
// sits frozen or invents movement. Laid out as a column because the four names
// do not fit across the panel at its default width, and they stay readable
// however narrow the user drags it.

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import {
  IMPORT_PHASES,
  importPhaseName,
  importPhaseStates,
  type PhaseState,
} from "../../../../features/imports/importPhases";
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";
import styles from "./ImportStepper.module.css";

function Marker({ state }: { state: PhaseState }) {
  // The row carries the accessible name, state included — a second "Loading"
  // per phase would only crowd it.
  if (state === "current") return <Spinner size={12} decorative />;
  const type = state === "done" ? "check_circle" : state === "failed" ? "error_outline" : "radio_button_unchecked";
  return <Icon category="outlined" type={type} />;
}

export function ImportStepper({ task }: { task: TaskViewModel }) {
  const { t } = useTranslation();
  // Nothing left to follow once every phase is behind it; the card's own badge
  // and timestamp say what became of it.
  if (task.state === "succeeded") return null;
  const states = importPhaseStates(task);

  return (
    <ol className={styles.stepper}>
      {IMPORT_PHASES.map((phase, i) => (
        // The rail's two halves are coloured separately: the segment above a
        // marker belongs to the phase above it, the one below to this phase.
        <li
          key={phase}
          className={styles.row}
          data-state={states[i]}
          data-prev={states[i - 1]}
          aria-label={`${importPhaseName(phase, t)} — ${t(`rework.imports.phaseState.${states[i]}`)}`}
          aria-current={states[i] === "current" ? "step" : undefined}
        >
          <span className={styles.rail} aria-hidden>
            <Marker state={states[i]} />
          </span>
          <span className={styles.label}>{importPhaseName(phase, t)}</span>
        </li>
      ))}
    </ol>
  );
}
