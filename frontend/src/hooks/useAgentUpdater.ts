// src/components/agentHub/hooks/useAgentUpdater.ts

import { useTranslation } from "react-i18next";
import { AnyAgent } from "../common/agent";
import { useToast } from "../components/ToastProvider";
import { Leader, useUpdateAgentAgenticV1AgentsUpdatePutMutation } from "../slices/agentic/agenticOpenApi";

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
    // The cast to AnyAgent is clean here as the type definition ensures correct properties
    const payload: AnyAgent = { ...agent, enabled };

    try {
      // The mutation expects a type compatible with Agent | Leader, which AnyAgent is.
      return await mutate({ agentSettings: payload }).unwrap();
    } catch (e: unknown) {
      handleUpdateError(e, t("agentHub.errors.updateFailed"));
    }
  };

  const updateTuning = async (
    agent: AnyAgent,
    newTuning: NonNullable<AnyAgent["tuning"]>,
  ) => {
    // The cast to AnyAgent is clean here as the type definition ensures correct properties
    const payload: AnyAgent = { ...agent, tuning: newTuning };

    try {
      // The mutation expects a type compatible with Agent | Leader, which AnyAgent is.
      return await mutate({ agentSettings: payload }).unwrap();
    } catch (e: unknown) {
      handleUpdateError(e, t("agentHub.errors.tuningUpdateFailed"));
    }
  };

  const updateLeaderCrew = async (leader: Leader & { type: "leader" }, crew: string[]) => {
    // The payload is already guaranteed to be a Leader | AnyAgent
    const payload: AnyAgent = { ...leader, crew };

    try {
      // The mutation expects a type compatible with Agent | Leader, which AnyAgent is.
      return await mutate({ agentSettings: payload }).unwrap();
    } catch (e: unknown) {
      handleUpdateError(e, t("agentHub.errors.crewUpdateFailed"));
    }
  };

  return { updateEnabled, updateTuning, updateLeaderCrew, isLoading: meta.isLoading };
}
