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

import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { IconType } from "@shared/utils/Type.ts";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import styles from "./TeamAgentEmptyState.module.scss";

interface TeamAgentEmptyStateProps {
  canManageAgents: boolean;
  templatesUnavailable: boolean;
  onCreateAgent: () => void;
}

export default function TeamAgentEmptyState({
  canManageAgents,
  templatesUnavailable,
  onCreateAgent,
}: TeamAgentEmptyStateProps) {
  const { agentIconName, agentsNicknameSingular } = useFrontendProperties();
  const { t } = useTranslation();

  return (
    <div className={styles.teamAgentEmptyState}>
      <div className={styles.teamAgentEmptyStatePresentation}>
        <span className={styles.teamAgentEmptyStateIcon}>
          <Icon category={"outlined"} type={agentIconName as IconType} filled={true} />
        </span>
        <span>{t("rework.teams.agents.noAgent", { agentsNicknameSingular })}</span>
      </div>
      {canManageAgents && (
        <Button
          color={"primary"}
          variant={"filled"}
          size={"medium"}
          icon={{ category: "outlined", type: "add" }}
          onClick={onCreateAgent}
          disabled={templatesUnavailable}
        >
          {t("rework.teams.agents.firstCreate", { agentsNicknameSingular })}
        </Button>
      )}
    </div>
  );
}
