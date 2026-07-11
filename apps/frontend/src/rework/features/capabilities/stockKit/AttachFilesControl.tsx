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

// Stock chat-turn control for the MCP capability's `attach_files` widget
// (CAPAB-01 #1976, RFC §3.3). Extracted verbatim from the former bespoke
// `SearchConfig` molecule's "attach" row — triggers the composer's existing
// file-picker flow (`composer.onAttach`), unchanged.

import { useTranslation } from "react-i18next";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import type { CapabilityChatTurnControlProps } from "../types";

export function AttachFilesControl({ composer, onRequestClose }: CapabilityChatTurnControlProps) {
  const { t } = useTranslation();

  return (
    <MenuPopoverItem
      icon={{ category: "outlined", type: "attach_file" }}
      label={t("chatbot.attachFiles")}
      trailingIcon="add"
      onClick={() => {
        composer.onAttach();
        onRequestClose?.();
      }}
    />
  );
}
