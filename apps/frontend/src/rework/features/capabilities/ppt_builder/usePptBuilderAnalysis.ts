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

// CP owns the accepted file and preparation state; the capability owns previews.

import { useEffect, useMemo, useState } from "react";
import { useResolvePowerpointTemplateQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  useGetPptBuilderAnalysisQuery,
  useGetPptBuilderBuiltinQuery,
  type AnalysisStatusResponse,
  type TemplateInventory,
} from "./api/pptBuilderCapabilityOpenApi";
import { CAPABILITY_ID } from "./api/pptBuilderCapabilityApi";
import { useCapabilityRouted } from "../useCapabilityRouted";
import type { PreviewSource } from "./usePatternsPreview";
import {
  OVERRIDES_KEY,
  TEMPLATE_SHA_KEY,
  effectiveInventory,
  readOverrides,
  readTemplateSha,
  summarize,
  unmatchedOverrides,
  upsertOverride,
  type InventorySummary,
  type OverridePatch,
  type PatternOverride,
} from "./types";

/** The manifest's one upload slot key (AssetSlot.key on the backend). */
export const TEMPLATE_SLOT = "template";

const POLL_MS = 3000;
const NO_OVERRIDES: PatternOverride[] = [];

/** What the panel shows about the template. */
export type AnalysisPhase =
  | "builtin" // no template: the built-in template is used until CP preparation is connected
  | "staged" // a file is picked; it is analysed after the save
  | "unknown" // a template is saved but its analysis cannot be read (yet)
  | AnalysisStatusResponse["status"];

export function analysisPhase(args: {
  stagedFile: File | undefined;
  templateSha: string | null;
  status: AnalysisStatusResponse | undefined;
}): AnalysisPhase {
  if (args.stagedFile) return "staged";
  if (!args.templateSha) return "builtin";
  if (!args.status || args.status.template_sha256 !== args.templateSha) return "unknown";
  return args.status.status;
}

export function isInProgress(phase: AnalysisPhase): boolean {
  return phase === "pending" || phase === "running";
}

/** Failed, interrupted, or produced by older analysis rules: worth a save that re-runs it. */
export function canRerun(phase: AnalysisPhase, status: AnalysisStatusResponse | undefined): boolean {
  return phase === "failed" || phase === "interrupted" || (phase === "succeeded" && status?.current === false);
}

interface Args {
  teamId?: string;
  agentInstanceId?: string;
  configValues: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
  assetFiles: Record<string, File | undefined>;
  onAssetFileChange: (slotKey: string, file: File | null) => void;
}

export interface PptBuilderAnalysis {
  templateSource?: "agent" | "organization" | "builtin";
  phase: AnalysisPhase;
  /** The saved template's status is still being fetched for the first time. */
  statusLoading: boolean;
  stagedFile: File | undefined;
  hasPersistedTemplate: boolean;
  /** The analysis error, or the interruption notice, as the backend words it. */
  error: string | null;
  canRerun: boolean;
  /** An outdated analysis is being re-read; its old inventory is shown meanwhile. */
  refreshing: boolean;
  /** The inventory with the overrides applied (what the agent will see). */
  effective: TemplateInventory | null;
  summary: InventorySummary | null;
  /** Overrides the analysed template no longer matches (dropped on save). */
  droppedOverrides: string[];
  previewSource: PreviewSource;
  overrides: PatternOverride[];
  updateOverride: (patternId: string, patch: OverridePatch) => void;
  handlePick: (file: File) => void;
  handleClear: () => void;
  handleUsePlatformTemplate: () => void;
}

export function usePptBuilderAnalysis({
  teamId,
  agentInstanceId,
  configValues,
  onConfigChange,
  assetFiles,
  onAssetFileChange,
}: Args): PptBuilderAnalysis {
  const routed = useCapabilityRouted(CAPABILITY_ID);
  const stagedFile = assetFiles[TEMPLATE_SLOT];
  const saved = useResolvePowerpointTemplateQuery(
    { spaceId: teamId ?? "", agentInstanceId: agentInstanceId ?? "" },
    { skip: !teamId || !agentInstanceId, pollingInterval: POLL_MS, refetchOnMountOrArgChange: true },
  );
  const removed = configValues.remove_template === true;
  const templateSha = removed ? null : (saved.currentData?.file?.sha256 ?? readTemplateSha(configValues));
  const analysisId = saved.currentData?.analysis_reference;
  const overrides = readOverrides(configValues);

  const [pollingInterval, setPollingInterval] = useState(0);
  const statusQuery = useGetPptBuilderAnalysisQuery(
    { instanceId: analysisId ?? "", spaceId: teamId, agentInstanceId },
    { skip: !routed || !analysisId || !templateSha, pollingInterval },
  );
  // A failed poll keeps the last answer (RTK keeps `data`): one network blip must
  // neither hide the analysis nor stop the polling of one in progress.
  const status = statusQuery.data;
  const phase: AnalysisPhase = stagedFile
    ? "staged"
    : !removed && saved.currentData?.preparation_state === "pending"
      ? "pending"
      : !removed && saved.currentData?.preparation_state === "failed"
        ? "failed"
        : analysisPhase({ stagedFile, templateSha, status });
  const refreshing = phase === "succeeded" && status?.refreshing === true;
  const usesBuiltin = phase === "builtin";
  const { data: builtin } = useGetPptBuilderBuiltinQuery(
    {},
    {
      skip: !usesBuiltin || !routed,
    },
  );

  // A refresh keeps the row succeeded: poll it too, so its new inventory shows when it ends.
  useEffect(() => {
    setPollingInterval(isInProgress(phase) || refreshing ? POLL_MS : 0);
  }, [phase, refreshing]);

  const inventory: TemplateInventory | null =
    phase === "succeeded" ? (status?.inventory ?? null) : usesBuiltin ? (builtin?.inventory ?? null) : null;
  const appliedOverrides = usesBuiltin ? NO_OVERRIDES : overrides;
  const effective = useMemo(
    () => (inventory ? effectiveInventory(inventory, appliedOverrides) : null),
    [inventory, appliedOverrides],
  );
  const droppedOverrides = useMemo(
    () => (inventory && !usesBuiltin ? unmatchedOverrides(overrides, inventory) : []),
    [inventory, usesBuiltin, overrides],
  );

  const previewSource: PreviewSource = usesBuiltin
    ? { kind: "builtin" }
    : phase === "succeeded" && status?.has_thumbnails && analysisId
      ? { kind: "analysis", instanceId: analysisId, spaceId: teamId, agentInstanceId }
      : null;

  return {
    templateSource: removed ? "builtin" : saved.currentData?.source,
    phase,
    statusLoading: statusQuery.isLoading || saved.isLoading,
    stagedFile,
    hasPersistedTemplate: templateSha !== null,
    error:
      phase === "failed" || phase === "interrupted"
        ? (saved.currentData?.preparation_error ?? status?.error ?? null)
        : null,
    canRerun: Boolean(agentInstanceId) && canRerun(phase, status),
    refreshing,
    effective,
    summary: effective ? summarize(effective) : null,
    droppedOverrides,
    previewSource,
    overrides,
    updateOverride: (patternId, patch) => onConfigChange(OVERRIDES_KEY, upsertOverride(overrides, patternId, patch)),
    handlePick: (file) => {
      onConfigChange("remove_template", false);
      onAssetFileChange(TEMPLATE_SLOT, file);
    },
    handleClear: () => onAssetFileChange(TEMPLATE_SLOT, null),
    handleUsePlatformTemplate: () => {
      onConfigChange("remove_template", true);
      onAssetFileChange(TEMPLATE_SLOT, null);
      onConfigChange(TEMPLATE_SHA_KEY, null);
      onConfigChange("template_key", null);
      onConfigChange(OVERRIDES_KEY, []);
    },
  };
}
