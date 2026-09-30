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

// Where a file has got to, as the two things that actually happen to it.
//
// Not a progress bar: the server reports one coarse step for the whole heavy
// phase, so a bar either sits frozen or has to invent movement. Two named
// phases, each either waiting, running, done or failed, say strictly what is
// known and never suggest a percentage nobody measured.

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { TERMINAL_STATES, type TaskViewModel } from "../../../../features/tasks/taskTypes";
import styles from "./ImportStepper.module.css";

type PhaseState = "pending" | "current" | "done" | "failed";

/** The transfer, then the analysis — see `ImportStage`. */
function phasesOf(task: TaskViewModel): [PhaseState, PhaseState] {
  const stopped = task.state === "failed" || task.state === "cancelled";
  // A file the browser is still sending, or one whose name is waiting on an
  // answer, has not reached the server's half.
  const beforeAnalysis = task.stage === "upload" || task.stage === "decision";

  if (beforeAnalysis) {
    if (stopped) return ["failed", "pending"];
    // Waiting on the user is not the transfer running; it is over and held.
    return [task.stage === "decision" ? "done" : "current", "pending"];
  }
  if (stopped) return ["done", "failed"];
  if (task.state === "succeeded") return ["done", "done"];
  return ["done", "current"];
}

function Marker({ state }: { state: PhaseState }) {
  if (state === "current") return <Spinner size={12} />;
  const type = state === "done" ? "check_circle" : state === "failed" ? "error_outline" : "radio_button_unchecked";
  return <Icon category="outlined" type={type} />;
}

export function ImportStepper({ task }: { task: TaskViewModel }) {
  const { t } = useTranslation();
  const [upload, analysis] = phasesOf(task);
  // Nothing left to follow once both halves are behind it; the card's own
  // badge and timestamp say what became of it.
  if (TERMINAL_STATES.has(task.state) && task.state === "succeeded") return null;

  return (
    <div className={styles.stepper} role="list">
      <span className={styles.phase} data-state={upload} role="listitem">
        <Marker state={upload} />
        {t("rework.imports.step.upload")}
      </span>
      <span className={styles.link} data-state={upload} aria-hidden />
      <span className={styles.phase} data-state={analysis} role="listitem">
        <Marker state={analysis} />
        {t("rework.imports.step.analysis")}
      </span>
    </div>
  );
}
