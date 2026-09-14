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

// Shared ppt_builder template orchestration, consumed by the Advanced-view
// config widget and the Simple-view pack options. Owns the upload → stateless
// `/analyze` round-trip, which inventory the review shows (staged analysis,
// else the saved one, else the built-in theme), the author's overrides
// (written back through `onConfigChange`), and the Save-gating error. A
// template is optional: only an unreadable staged file blocks Save.

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useAnalyzePptBuilderTemplateMutation,
  useGetPptBuilderThemeQuery,
  type AnalyzeResult,
  type BodyAnalyzePptBuilderTemplate,
  type TemplateInventory,
} from "./api/pptBuilderCapabilityOpenApi";
import { CAPABILITY_ID } from "./api/pptBuilderCapabilityApi";
import { useCapabilityRouted } from "../useCapabilityRouted";
import type { PreviewSource } from "./usePatternsPreview";
import {
  OVERRIDES_KEY,
  PATTERNS_PATH_KEY,
  effectiveInventory,
  readInventory,
  readOverrides,
  summarize,
  upsertOverride,
  type InventorySummary,
  type PatternOverride,
} from "./types";

/** The manifest's one upload slot key (AssetSlot.key on the backend). */
export const TEMPLATE_SLOT = "template";

interface Args {
  configValues: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
  assetFiles: Record<string, File | undefined>;
  onAssetFileChange: (slotKey: string, file: File | null) => void;
  onBlockingErrorChange: (message: string | null) => void;
}

export interface PptBuilderAnalysis {
  stagedFile: File | undefined;
  hasPersistedTemplate: boolean;
  isAnalyzing: boolean;
  analyzeFailed: boolean;
  /** Analysis errors of the staged file (empty when clean or not staged). */
  errors: AnalyzeResult["errors"];
  /** What the review shows: staged analysis, saved inventory, or the theme. */
  inventory: TemplateInventory | null;
  /** The inventory with the overrides applied (what the agent will see). */
  effective: TemplateInventory | null;
  summary: InventorySummary | null;
  usesTheme: boolean;
  previewSource: PreviewSource;
  overrides: PatternOverride[];
  updateOverride: (patternId: string, patch: Partial<Omit<PatternOverride, "pattern_id">>) => void;
  blockingError: string | null;
  handlePick: (file: File) => Promise<void>;
  handleClear: () => void;
}

export function usePptBuilderAnalysis({
  configValues,
  onConfigChange,
  assetFiles,
  onAssetFileChange,
  onBlockingErrorChange,
}: Args): PptBuilderAnalysis {
  const { t } = useTranslation();
  const routed = useCapabilityRouted(CAPABILITY_ID);
  const [analyze, { isLoading: isAnalyzing }] = useAnalyzePptBuilderTemplateMutation();
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);
  const [analyzeFailed, setAnalyzeFailed] = useState(false);

  const stagedFile = assetFiles[TEMPLATE_SLOT];
  const persisted = readInventory(configValues);
  const hasPersistedTemplate = persisted !== null;
  const usesTheme = !stagedFile && !hasPersistedTemplate;
  const { data: theme } = useGetPptBuilderThemeQuery(undefined, { skip: !usesTheme || !routed });

  const inventory: TemplateInventory | null = stagedFile
    ? (analysis?.inventory ?? null)
    : (persisted ?? theme?.inventory ?? null);
  const errors = stagedFile ? (analysis?.errors ?? []) : [];
  const overrides = readOverrides(configValues);
  const effective = useMemo(
    () => (inventory ? effectiveInventory(inventory, overrides) : null),
    [inventory, overrides],
  );
  const summary = effective ? summarize(effective) : null;

  const patternsPath = configValues[PATTERNS_PATH_KEY];
  const previewSource: PreviewSource = stagedFile
    ? analysis?.inventory
      ? { kind: "staged", file: stagedFile }
      : null
    : hasPersistedTemplate
      ? typeof patternsPath === "string" && patternsPath
        ? { kind: "persisted", path: patternsPath }
        : null
      : { kind: "theme" };

  const blockingError = useMemo(() => {
    if (stagedFile && (analyzeFailed || errors.length > 0)) return t("capability.ppt_builder.form.templateInvalid");
    return null;
  }, [stagedFile, analyzeFailed, errors.length, t]);

  useEffect(() => {
    onBlockingErrorChange(blockingError);
    // Clearing on unmount keeps a deselected capability from blocking Save.
    return () => onBlockingErrorChange(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blockingError]);

  const handlePick = async (file: File) => {
    onAssetFileChange(TEMPLATE_SLOT, file);
    setAnalysis(null);
    setAnalyzeFailed(false);
    try {
      // The generated client cannot express multipart; the FormData body cast
      // is the sanctioned narrow exception (types still come from the client).
      const formData = new FormData();
      formData.append("file", file, file.name);
      const result = await analyze({
        bodyAnalyzePptBuilderTemplate: formData as unknown as BodyAnalyzePptBuilderTemplate,
      }).unwrap();
      setAnalysis(result);
    } catch {
      setAnalyzeFailed(true);
    }
  };

  const handleClear = () => {
    onAssetFileChange(TEMPLATE_SLOT, null);
    setAnalysis(null);
    setAnalyzeFailed(false);
  };

  const updateOverride = (patternId: string, patch: Partial<Omit<PatternOverride, "pattern_id">>) => {
    onConfigChange(OVERRIDES_KEY, upsertOverride(overrides, patternId, patch));
  };

  return {
    stagedFile,
    hasPersistedTemplate,
    isAnalyzing,
    analyzeFailed,
    errors,
    inventory,
    effective,
    summary,
    usesTheme,
    previewSource,
    overrides,
    updateOverride,
    blockingError,
    handlePick,
    handleClear,
  };
}
