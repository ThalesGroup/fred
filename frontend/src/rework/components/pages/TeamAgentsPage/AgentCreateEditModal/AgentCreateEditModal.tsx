import styles from "./AgentCreateEditModal.module.css";
import Button from "@shared/atoms/Button/Button.tsx";
import { ModalInteractionProps } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { IconType } from "@shared/utils/Type.ts";
import { AnyAgent } from "../../../../../common/agent.ts";
import { useRef, useState } from "react";
import { AgentCreateEditForm, CreationFormCallback } from "../../../../../components/agentHub/AgentCreateEditForm.tsx";

interface AgentCreateEditModalProps {
  modalInteraction: ModalInteractionProps;
  teamName: string;
  teamId: string;
  agent: AnyAgent | null;
  canDelete: boolean;
  onDeleted?: () => void;
  onSaved?: () => void;
}

export default function AgentCreateEditModal({
  modalInteraction,
  teamName,
  teamId,
  agent,
  canDelete,
  onDeleted,
  onSaved,
}: AgentCreateEditModalProps) {
  const { t } = useTranslation();
  const { agentsNicknameSingular, agentIconName } = useFrontendProperties();
  const isCreateMode = agent === null;
  const childRef = useRef<CreationFormCallback>(null);
  const [isSaveDisabled, setIsSaveDisabled] = useState(true);

  const handleDelete = () => {
    childRef.current.delete();
  };

  const handleSave = () => {
    childRef.current.save();
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
              {agent
                ? t("rework.teams.formAgent.titleEdit", { agent: agent.name })
                : t("rework.teams.formAgent.titleCreate", { agentsNicknameSingular })}
            </div>
            <div className={styles.agentCreateEditModalTeam}>{teamName}</div>
          </div>
        </div>
        <div className={styles.agentCreateEditModalActions}>
          <Button color={"primary"} variant={"text"} size={"medium"} onClick={modalInteraction.close}>
            {t("rework.cancel")}
          </Button>
          <Button color={"primary"} variant={"filled"} size={"medium"} onClick={handleSave} disabled={isSaveDisabled}>
            {isCreateMode ? t("rework.create") : t("rework.save")}
          </Button>
        </div>
      </div>
      <div className={styles.agentCreateEditModalContentWrapper}>
        <div className={styles.agentCreateEditModalContent}>
          <AgentCreateEditForm
            ref={childRef}
            agent={agent}
            canDelete={true}
            teamId={teamId}
            onClose={() => modalInteraction.close()}
            onSaved={onSaved}
            onDeleted={() => {
              onDeleted();
              modalInteraction.close();
            }}
            onValidityChange={setIsSaveDisabled}
          />
        </div>
        {!isCreateMode && (
          <div className={styles.deleteAction}>
            <Button color={"error"} variant={"filled"} size={"medium"} onClick={handleDelete} disabled={!canDelete}>
              {t("common.delete")}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
