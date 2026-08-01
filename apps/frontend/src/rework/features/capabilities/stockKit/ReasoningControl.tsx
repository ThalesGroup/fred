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

// Stock chat-turn control for the platform-owned `reasoning_toggle` widget
// (REASON-01 level 4, MODEL-REASONING-ENABLEMENT-RFC.md §7 + §15).
//
// It lives in the capability-agnostic stock kit rather than a plugin folder
// because reasoning is NOT a capability (§15): control-plane emits this
// descriptor itself, under the reserved `platform` owner, and resolution falls
// through to the stock kit by widget id.
//
// `params.default` only seeds `useComposerSettings`'s initial value (off);
// this row reads and writes the live `composer.reasoning` state, which travels
// to the pod on `RuntimeContext.reasoning` — the same channel as the search
// policy, not a capability's typed `turn_options` slice.
//
// The row's mere presence already means every upstream gate is open: the model
// can reason, a platform admin enabled it, and the agent's author offered the
// control (§8 — a control whose upstream gate is closed is never rendered, it
// is dropped at session prep).

import { useTranslation } from "react-i18next";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import type { CapabilityChatTurnControlProps } from "../types";

export interface ReasoningToggleControlParams {
  default?: boolean;
}

export function ReasoningControl({ composer }: CapabilityChatTurnControlProps) {
  const { t } = useTranslation();
  const on = composer.reasoning;

  return (
    <MenuPopoverItem
      icon={{ category: "outlined", type: "auto_awesome" }}
      label={t("chatbot.composerSettings.reasoningRowLabel")}
      // A switch, like the two admin-side reasoning controls it continues: the
      // same on/off state should not read as a checkbox here and a switch on
      // the agent form. The row itself is the control (see `trailingToggle`),
      // so it does not open a submenu and the popover stays open — flip it and
      // keep composing.
      trailingToggle
      selected={on}
      onClick={() => composer.onReasoningChange(!on)}
    />
  );
}
