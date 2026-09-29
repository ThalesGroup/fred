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

import { useTranslation } from "react-i18next";
import { EnumSelectRow } from "@shared/molecules/EnumSelectRow/EnumSelectRow";
import type { CapabilityChatTurnControlProps } from "../types";

export function AskUserToggleControl({ composer, open, onToggleOpen }: CapabilityChatTurnControlProps) {
  const { t } = useTranslation();
  return (
    <EnumSelectRow
      icon={{ category: "outlined", type: "help" }}
      label={t("chatbot.composerSettings.askUserLabel")}
      title={t("chatbot.composerSettings.askUserTitle")}
      value={composer.askUser ? "on" : "off"}
      options={[
        { value: "on", label: t("chatbot.composerSettings.askUserOn") },
        { value: "off", label: t("chatbot.composerSettings.askUserOff") },
      ]}
      open={open}
      onToggle={onToggleOpen}
      onChange={(value) => {
        composer.onAskUserChange(value === "on");
        onToggleOpen();
      }}
    />
  );
}
