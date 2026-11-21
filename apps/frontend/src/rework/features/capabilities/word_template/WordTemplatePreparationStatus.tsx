// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { useAgentReadinessCheckMutation } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  useGetTeamAgentPreparationsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPreparationsGetQuery as usePreparations,
  usePostTeamAgentPreparationRetryControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPreparationsCapabilityIdRetryPostMutation as useRetry,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./WordTemplateLibraryForm.module.css";

interface Props {
  teamId?: string;
  agentInstanceId?: string;
  staged: boolean;
  hasLibrary: boolean;
}

export function WordTemplatePreparationStatus({ teamId, agentInstanceId, staged, hasLibrary }: Props) {
  const { t } = useTranslation();
  const { agentsNicknameSingular } = useFrontendProperties();
  const args = { teamId: teamId ?? "", agentInstanceId: agentInstanceId ?? "" };
  const query = usePreparations(args, {
    skip: !teamId || !agentInstanceId || !hasLibrary,
    pollingInterval: 3000,
  });
  const status = query.data?.items.find((item) => item.capability_id === "word_template");
  const [retry, retryState] = useRetry();
  const [retryError, setRetryError] = useState(false);
  const [checkReadiness] = useAgentReadinessCheckMutation();
  const checked = useRef<string | null>(null);

  useEffect(() => {
    if (!teamId || !agentInstanceId || !status || status.state === "pending" || status.state === "running") return;
    if (checked.current === status.preparation_id) return;
    checked.current = status.preparation_id;
    void checkReadiness({ teamId, agentInstanceId });
  }, [teamId, agentInstanceId, status, checkReadiness]);

  if (staged)
    return (
      <p className={styles.description}>
        {t("capability.word_template.preparation.staged", { agentsNicknameSingular })}
      </p>
    );
  if (!hasLibrary || !status) return null;
  const busy = status.state === "pending" || status.state === "running";
  return (
    <div role={status.state === "failed" ? "alert" : "status"}>
      <p className={styles.description}>
        {busy && <Spinner size={16} />}{" "}
        {t(`capability.word_template.preparation.${status.state}`, { agentsNicknameSingular })}
      </p>
      {status.state === "failed" && (
        <Button
          color="primary"
          variant="outlined"
          size="small"
          disabled={retryState.isLoading}
          onClick={() => {
            setRetryError(false);
            void retry({ ...args, capabilityId: "word_template" })
              .unwrap()
              .then(() => query.refetch())
              .catch(() => setRetryError(true));
          }}
        >
          {t("capability.word_template.preparation.retry")}
        </Button>
      )}
      {retryError && <p role="alert">{t("capability.word_template.preparation.retryError")}</p>}
    </div>
  );
}
