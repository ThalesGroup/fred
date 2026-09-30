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

// Where a file has got to, as the four phases it actually goes through.
//
// Not a progress bar: no phase reports a fraction of itself, so a bar either
// sits frozen or invents movement. Markers only — it sits in the card's footer
// facing the name of the phase in flight, and that name is what says which
// marker is spinning. The caller decides when to show it; once the file is
// settled the footer goes back to its timestamp.

import { Fragment } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import {
  IMPORT_PHASES,
  importLinkStates,
  importPhaseHint,
  importPhaseName,
  importPhaseStates,
  type PhaseState,
} from "../../../../features/imports/importPhases";
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";
import styles from "./ImportStepper.module.css";

function Marker({ state }: { state: PhaseState }) {
  // The phase carries the accessible name, state included — a second
  // "Loading" per phase would only crowd it.
  if (state === "current") return <Spinner size={12} decorative />;
  const type = state === "done" ? "check_circle" : state === "failed" ? "error_outline" : "radio_button_unchecked";
  return <Icon category="outlined" type={type} />;
}

export function ImportStepper({ task }: { task: TaskViewModel }) {
  const { t } = useTranslation();
  const states = importPhaseStates(task);
  const links = importLinkStates(states);

  return (
    <ol className={styles.stepper} aria-label={t("rework.imports.stepper.label")}>
      {IMPORT_PHASES.map((phase, i) => (
        <Fragment key={phase}>
          {i > 0 && <li className={styles.link} data-state={links[i - 1]} aria-hidden />}
          <li
            className={styles.phase}
            data-state={states[i]}
            aria-label={`${importPhaseName(phase, t)} — ${t(`rework.imports.phaseState.${states[i]}`)}`}
            aria-current={states[i] === "current" ? "step" : undefined}
          >
            {/* Inside the <li>, not around it: the Tooltip renders a <span>,
                which between <ol> and <li> would break the list. */}
            <Tooltip
              content={
                <span className={styles.tip}>
                  <span className={styles.tipName}>{importPhaseName(phase, t)}</span>
                  <span className={styles.tipHint}>{importPhaseHint(phase, t)}</span>
                </span>
              }
            >
              <span className={styles.marker}>
                <Marker state={states[i]} />
              </span>
            </Tooltip>
          </li>
        </Fragment>
      ))}
    </ol>
  );
}
