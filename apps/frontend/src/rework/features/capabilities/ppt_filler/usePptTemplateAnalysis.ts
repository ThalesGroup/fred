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

// Shared ppt_filler template-upload orchestration (#1903), consumed by BOTH the
// Advanced-view config widget (PptFillerConfigForm) and the Simple-view capability
// pack options (PptFillerPackOptions). Kept as one hook so the analyze call, the
// Save-gating blocking error, and the per-slide error i18n never drift between the
// two surfaces — presentation stays in each component, this owns the logic only.

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useAnalyzeAnalyzePostMutation,
  type BodyAnalyzeAnalyzePost,
  type ParseResult,
  type SlideSchema,
  type TemplateError,
} from "./api/pptFillerCapabilityOpenApi";

/** The manifest's one upload slot key (AssetSlot.key on the backend). */
export const TEMPLATE_SLOT = "template";

/**
 * i18n an error by its stable code (the RFC contract: `code` is the machine
 * key, `message` the English fallback). Unknown codes fall back to the
 * backend-provided message so a new code never renders blank.
 */
export function useTemplateErrorText() {
  const { t } = useTranslation();
  return (error: TemplateError): string =>
    t(`capability.ppt_filler.errors.${error.code}`, {
      defaultValue: error.message,
      slide: error.slide,
      // The literal `{{key}}` placeholder is prebuilt here — braces inside an
      // i18next template would be parsed as interpolation markers.
      placeholder: `{{${error.key}}}`,
    });
}

interface UsePptTemplateAnalysisArgs {
  configValues: Record<string, unknown>;
  assetFiles: Record<string, File | undefined>;
  onAssetFileChange: (slotKey: string, file: File | null) => void;
  onBlockingErrorChange: (message: string | null) => void;
}

export interface PptTemplateAnalysis {
  stagedFile: File | undefined;
  hasPersistedTemplate: boolean;
  isAnalyzing: boolean;
  analyzeFailed: boolean;
  /** Slide schema of the current preview source (staged analysis, else persisted). */
  previewSlides: SlideSchema[];
  /** Validation errors for the staged file (empty for a clean or persisted template). */
  previewErrors: TemplateError[];
  /** Save-gating message (template missing / invalid), or null when the config is valid. */
  blockingError: string | null;
  /** True once a freshly staged file has analyzed cleanly (no errors). */
  stagedAnalyzedClean: boolean;
  handlePick: (file: File) => Promise<void>;
  handleClear: () => void;
  errorText: (error: TemplateError) => string;
}

/**
 * Owns the upload → stateless `/analyze` → preview/validation lifecycle for the
 * ppt_filler template slot. The uploaded file itself travels with the atomic
 * save (multipart with-assets endpoints); this analysis never persists anything.
 */
export function usePptTemplateAnalysis({
  configValues,
  assetFiles,
  onAssetFileChange,
  onBlockingErrorChange,
}: UsePptTemplateAnalysisArgs): PptTemplateAnalysis {
  const { t } = useTranslation();
  const errorText = useTemplateErrorText();
  const [analyze, { isLoading: isAnalyzing }] = useAnalyzeAnalyzePostMutation();
  const [analysis, setAnalysis] = useState<ParseResult | null>(null);
  const [analyzeFailed, setAnalyzeFailed] = useState(false);

  const stagedFile = assetFiles[TEMPLATE_SLOT];
  const persistedSchema = (configValues.schema_slides as SlideSchema[] | undefined) ?? [];
  const hasPersistedTemplate = persistedSchema.length > 0;

  // What the preview shows: the staged file's live analysis when one is
  // picked, else the persisted schema (source of truth: the saved template).
  const previewSlides = stagedFile ? (analysis?.schema ?? []) : persistedSchema;
  const previewErrors = stagedFile ? (analysis?.errors ?? []) : [];

  const blockingError = useMemo(() => {
    if (!stagedFile && !hasPersistedTemplate) return t("capability.ppt_filler.form.templateRequired");
    if (stagedFile && previewErrors.length > 0) return t("capability.ppt_filler.form.templateInvalid");
    return null;
  }, [stagedFile, hasPersistedTemplate, previewErrors.length, t]);

  useEffect(() => {
    onBlockingErrorChange(blockingError);
    // Clearing on unmount keeps a deselected capability from blocking Save.
    return () => onBlockingErrorChange(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blockingError]);

  // Only true right after a staged file analyzes with no errors — lets a caller
  // (the pack options) fire a one-shot "upload succeeded" toast.
  const stagedAnalyzedClean = Boolean(stagedFile) && analysis !== null && (analysis?.errors ?? []).length === 0;

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
        bodyAnalyzeAnalyzePost: formData as unknown as BodyAnalyzeAnalyzePost,
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

  return {
    stagedFile,
    hasPersistedTemplate,
    isAnalyzing,
    analyzeFailed,
    previewSlides,
    previewErrors,
    blockingError,
    stagedAnalyzedClean,
    handlePick,
    handleClear,
    errorText,
  };
}
