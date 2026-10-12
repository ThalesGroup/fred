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
import Icon from "@shared/atoms/Icon/Icon";
import type { CommandDescriptor } from "../../../../../slices/runtime/runtimeOpenApi";
import styles from "./CommandTurn.module.css";

interface CommandTurnProps {
  command: CommandDescriptor;
  inline?: boolean;
  /** Opens the prompt this turn actually sent. Omit to render it inert. */
  onOpen?: () => void;
}

/** A user turn launched by a prompt command, shown as the command rather than
 *  the prompt behind it. A button, not a decorated span: opening the prompt
 *  must not be a click-only path. */
export function CommandTurn({ command, onOpen, inline = false }: CommandTurnProps) {
  const { t } = useTranslation();
  const appended = inline ? undefined : command.appended_text?.trim();

  return (
    <button
      type="button"
      className={styles.command}
      onClick={onOpen}
      disabled={!onOpen}
      aria-label={
        appended
          ? t("chatbot.commandTurn.openWithText", { command: command.command, appended })
          : t("chatbot.commandTurn.open", { command: command.command })
      }
    >
      <span className={styles.slug}>
        <Icon category="outlined" type="edit_note" />
        <span>/{command.command}</span>
      </span>
      {appended && <span className={styles.appended}> {appended}</span>}
    </button>
  );
}
