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

import { useId } from "react";
import { useTranslation } from "react-i18next";
import { useLocalStorageState } from "../../../../../hooks/useLocalStorageState";
import type { AgentTodo, AgentTodoStatus } from "../../../../utils/agentTodo";
import Icon from "../../atoms/Icon/Icon";
import styles from "./AgentTodoPanel.module.css";

interface AgentTodoPanelProps {
  sessionId: string;
  todos: readonly AgentTodo[];
}

const STATUS_ICONS = {
  pending: "radio_button_unchecked",
  in_progress: "sync",
  completed: "check_circle",
} as const;

function preferenceKey(sessionId: string): string {
  return `agentTodoPanelExpanded.${sessionId}`;
}

export function AgentTodoPanel({ sessionId, todos }: AgentTodoPanelProps) {
  const { t } = useTranslation();
  const bodyId = useId();
  const remaining = todos.filter((todo) => todo.status !== "completed").length;
  const [preference, setPreference] = useLocalStorageState<boolean | null>(preferenceKey(sessionId), null);
  const expanded = preference ?? remaining > 0;

  if (todos.length === 0 || remaining === 0) return null;

  const statusLabel = (status: AgentTodoStatus) => t(`rework.agentTodoPanel.status.${status}`);

  return (
    <section className={styles.root} aria-label={t("rework.agentTodoPanel.ariaLabel")}>
      <button
        type="button"
        className={styles.toggle}
        onClick={() => setPreference(!expanded)}
        aria-expanded={expanded}
        aria-controls={bodyId}
      >
        <span className={styles.heading}>{t("rework.agentTodoPanel.title")}</span>
        <span className={styles.progress}>{t("rework.agentTodoPanel.remaining", { count: remaining })}</span>
        <span className={styles.chevron} aria-hidden="true">
          <Icon category="outlined" type={expanded ? "expand_less" : "expand_more"} />
        </span>
      </button>

      {expanded && (
        <ul id={bodyId} className={styles.list}>
          {todos.map((todo, index) => (
            <li
              key={`${index}:${todo.content}`}
              className={`${styles.item} ${styles[todo.status]}`}
              aria-label={`${statusLabel(todo.status)}: ${todo.content}`}
            >
              <span className={styles.statusIcon} aria-hidden="true">
                <Icon category="outlined" type={STATUS_ICONS[todo.status]} filled={todo.status === "completed"} />
              </span>
              <span className={styles.content}>{todo.content}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
