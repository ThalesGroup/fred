// src/components/agentHub/hooks/useAgentUpdater.ts

import { useTranslation } from "react-i18next";
import { AnyAgent } from "../common/agent";
import { useToast } from "../components/ToastProvider";
import { Agent2, useUpdateAgentAgenticV1AgentsUpdatePutMutation } from "../slices/agentic/agenticOpenApi";

// Helper to normalize the error structure from the API (RTK Query error structure)
type ApiError = { data?: { detail?: string | string[] } } | Error;

export function useAgentUpdater() {
  const [mutate, meta] = useUpdateAgentAgenticV1AgentsUpdatePutMutation();
  const { showError } = useToast();
  const { t } = useTranslation();

  // --- Simplified Error Handler ---
  const handleUpdateError = (e: unknown, defaultSummaryKey: string) => {
    const error = e as ApiError;
    // Attempt to extract detail from RTK Query error structure (error.data.detail)
    const apiDetail =
      typeof (error as { data: any }).data === "object" && (error as { data: any }).data?.detail
        ? String((error as { data: any }).data.detail)
        : null;

    showError({
      summary: t(defaultSummaryKey),
      detail: apiDetail || (error instanceof Error ? error.message : t("validation.error")),
    });
    // Re-throw to allow calling components to handle error flow (e.g., stopping a loader)
    throw error;
  };
  // -------------------------------------

  const updateEnabled = async (agent: AnyAgent, enabled: boolean) => {
    const payload: Agent2 = { ...agent, enabled };

    try {
      return await mutate({ agentInput: payload }).unwrap();
    } catch (e: unknown) {
      handleUpdateError(e, t("agentHub.errors.updateFailed"));
    }
  };

  const updateTuning = async (agent: AnyAgent, newTuning: NonNullable<AnyAgent["tuning"]>) => {
    const payload: Agent2 = { ...agent, tuning: newTuning };

    try {
      return await mutate({ agentInput: payload }).unwrap();
    } catch (e: unknown) {
      handleUpdateError(e, t("agentHub.errors.tuningUpdateFailed"));
    }
  };

  return { updateEnabled, updateTuning, isLoading: meta.isLoading };
}
