// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import {
  useResolveWordTemplateLibraryQuery,
  useUpdateAgentInstanceMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./WordTemplateLibraryForm.module.css";

export function WordTemplatePreparationStatus({
  teamId,
  agentInstanceId,
  staged,
  hasLibrary,
  disabled = false,
}: {
  teamId?: string;
  agentInstanceId?: string;
  staged: boolean;
  hasLibrary: boolean;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const query = useResolveWordTemplateLibraryQuery(
    { spaceId: teamId ?? "", agentInstanceId },
    {
      skip: !teamId || !agentInstanceId || !hasLibrary,
      pollingInterval: 3000,
    },
  );
  const [updateAgent, retryState] = useUpdateAgentInstanceMutation();
  const retry = async () => {
    if (!teamId || !agentInstanceId || disabled || retryState.isLoading) return;
    try {
      await updateAgent({ spaceId: teamId, agentInstanceId, updateAgentInstanceRequest: {} }).unwrap();
      await query.refetch();
    } catch {
      /* Keep canonical polling; show the mutation error below. */
    }
  };
  if (staged) return <p className={styles.description}>{t("capability.word_template.preparation.staged")}</p>;
  if (!hasLibrary || !query.data) return null;
  const failed = query.data.files.find((file) => file.preparation_state === "failed");
  const pending = !failed && !query.data.activation_ready;
  return (
    <div role={failed ? "alert" : "status"}>
      <p className={styles.description}>
        {pending && <Spinner size={16} />}{" "}
        {t(`capability.word_template.preparation.${failed ? "failed" : pending ? "pending" : "ready"}`)}
        {failed?.preparation_error && ` ${failed.preparation_error}`}
      </p>
      {failed && query.data.source === "agent" && (
        <Button
          color="primary"
          variant="outlined"
          size="small"
          disabled={disabled || retryState.isLoading}
          onClick={() => void retry()}
        >
          {t("capability.word_template.preparation.retry")}
        </Button>
      )}
      {retryState.error && <p role="alert">{t("capability.word_template.preparation.retryError")}</p>}
    </div>
  );
}
