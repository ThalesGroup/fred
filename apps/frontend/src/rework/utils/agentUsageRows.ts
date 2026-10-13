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

import type { TFunction } from "i18next";
import type { LabelValuePoint } from "../../slices/controlPlane/controlPlaneOpenApi";

// Mirrors `CREATION_ASSISTANT_LABEL` in control-plane kpi/presets/common.py:
// the by-agent bucket for creation assistant calls, which have no agent.
export const CREATION_ASSISTANT_LABEL = "__creation_assistant__";

/** By-agent token rows with the creation assistant bucket translated. */
export function agentUsageRows(rows: LabelValuePoint[] | undefined, t: TFunction): LabelValuePoint[] {
  return (rows ?? []).map((row) =>
    row.label === CREATION_ASSISTANT_LABEL
      ? { ...row, label: t("rework.analytics.tokenUsage.byAgent.creationAssistant") }
      : row,
  );
}
