import styles from "./AgentCreateEditModal.module.css";
import Button from "@shared/atoms/Button/Button.tsx";
import { ModalInteractionProps } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { IconType } from "@shared/utils/Type.ts";
import { AnyAgent } from "../../../../../common/agent.ts";
import { useDeleteAgentAgenticV1AgentsAgentIdDeleteMutation } from "../../../../../slices/agentic/agenticOpenApi.ts";
import AgentV1CreateEditForm from "@components/pages/TeamAgentsPage/AgentCreateEditModal/AgentV1CreateEditForm/AgentV1CreateEditForm.tsx";
import { useState } from "react";

interface AgentCreateEditModalProps {
  modalInteraction: ModalInteractionProps;
  teamName: string;
  agent: AnyAgent | null;
  canDelete: boolean;
  onDeleted?: () => void;
}

class AgentVersion {}

class V2CreateMode {}

export default function AgentCreateEditModal({
  modalInteraction,
  teamName,
  agent,
  canDelete,
  onDeleted,
}: AgentCreateEditModalProps) {
  const { t } = useTranslation();
  const { agentsNicknameSingular, agentIconName } = useFrontendProperties();
  const isCreateMode = agent === null;

  const [agentVersion, setAgentVersion] = useState<AgentVersion>("v2");
  const [v2CreateMode, setV2CreateMode] = useState<V2CreateMode>("react");

  const [triggerDeleteAgent] = useDeleteAgentAgenticV1AgentsAgentIdDeleteMutation();

  const handleDelete = () => {
    if (!agent) return;
    triggerDeleteAgent({ agentId: agent.id }).unwrap();
    onDeleted();
    modalInteraction.close();
  };

  return (
    <div className={styles.agentCreateEditModalContainer}>
      <div className={styles.agentCreateEditModalHeader}>
        <div className={styles.agentCreateEditModalPresentation}>
          <span className={styles.icon}>
            <Icon category={"outlined"} type={agentIconName as IconType} filled={true} />
          </span>
          <div className={styles.agentCreateEditModalPresentationTitle}>
            <div className={styles.agentCreateEditModalTitle}>
              {t("rework.teams.formAgent.title", { agentsNicknameSingular })}
            </div>
            <div className={styles.agentCreateEditModalTeam}>{teamName}</div>
          </div>
        </div>
        <div className={styles.agentCreateEditModalActions}>
          <Button color={"primary"} variant={"text"} size={"medium"} onClick={modalInteraction.close}>
            {t("rework.cancel")}
          </Button>
          <Button color={"primary"} variant={"filled"} size={"medium"} onClick={modalInteraction.close}>
            {isCreateMode ? t("rework.create") : t("rework.save")}
          </Button>
          {!isCreateMode && (
            <Button color={"error"} variant={"filled"} size={"medium"} onClick={handleDelete} disabled={!canDelete}>
              {t("common.delete")}
            </Button>
          )}
        </div>
      </div>
      <div className={styles.agentCreateEditModalContent}>
        <AgentV1CreateEditForm />
      </div>
    </div>
  );
}
