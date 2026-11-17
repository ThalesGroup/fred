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

import { useId, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { CharacterLimitNotice } from "@shared/atoms/CharacterLimitNotice/CharacterLimitNotice";
import { countUnicodeCodePoints } from "@core/utils/chatInput.ts";
import { resolveAgentIcon } from "@shared/utils/agentIcon.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type { ManagedAgentInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { initialPromptState } from "../../ManagedChatPage/useInitialPrompt";
import AgentChatButton from "@shared/organisms/AgentCard/AgentChatButton.tsx";
import SectionMarker from "../SectionMarker/SectionMarker.tsx";
import styles from "./HomeAskBox.module.scss";

const MAX_HEIGHT_PX = 160;

interface HomeAskBoxProps {
  agent: ManagedAgentInstanceSummary;
  /** The agent pod's chat message limit; none when the home could not read it. */
  maxChars?: number;
}

/** Text-only question to the admin-chosen agent: opens a new conversation that sends it. */
export default function HomeAskBox({ agent, maxChars }: HomeAskBoxProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { agentIconName } = useFrontendProperties();
  const [text, setText] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);
  const question = text.trim();
  const limitId = useId();
  // Same count and notice as the chat composer, which enforces the limit again.
  const count = countUnicodeCodePoints(question);
  const tooLong = maxChars !== undefined && count > maxChars;

  const grow = () => {
    const element = field.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT_PX)}px`;
  };
  const submit = (event?: { preventDefault: () => void }) => {
    event?.preventDefault();
    if (!question || tooLong) return;
    navigate(`/team/${agent.team_id}/managed-chat/${agent.agent_instance_id}`, {
      state: initialPromptState(question),
    });
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  };

  return (
    <section className={styles.section} aria-labelledby="home-ask-title">
      <h2 id="home-ask-title" className={styles.title}>
        <SectionMarker />
        {t("rework.home.advanced.askTitle", { name: agent.display_name })}
      </h2>
      <form className={styles.box} onSubmit={submit}>
        <span className={styles.agent} aria-hidden="true">
          <Icon category="outlined" type={resolveAgentIcon(agent, agentIconName)} />
        </span>
        <textarea
          ref={field}
          className={styles.input}
          rows={1}
          value={text}
          placeholder={t("rework.home.advanced.askPlaceholder", { name: agent.display_name })}
          aria-label={t("rework.home.advanced.askLabel", { name: agent.display_name })}
          onChange={(event) => {
            setText(event.target.value);
            grow();
          }}
          onKeyDown={onKeyDown}
          aria-invalid={tooLong || undefined}
          aria-describedby={maxChars !== undefined ? limitId : undefined}
        />
        <AgentChatButton submit disabled={!question || tooLong} />
      </form>
      <CharacterLimitNotice id={limitId} count={count} limit={maxChars} />
      <p className={styles.hint}>{t("rework.home.advanced.askHint", { name: agent.display_name })}</p>
    </section>
  );
}
