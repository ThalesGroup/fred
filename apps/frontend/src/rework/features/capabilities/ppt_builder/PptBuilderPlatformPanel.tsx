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

// Swift admin drawer for the organization/pod default template. A replacement is analysed while
// the current one stays in use; the organization write permission gates actions.
// Without a common template, the manager reviews and corrects the Fred template.

import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSelector } from "react-redux";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { selectCapabilityBaseUrl, type CapabilityRoutingState } from "../../../../common/capabilityRoutingSlice";
import { downloadAuthed } from "../../../../utils/downloadUtils";
import { normalizeApiError } from "../../../core/errors/normalizeApiError";
import {
  useGetPowerpointSettingsQuery,
  usePutPowerpointSettingsMutation,
  useRerunPowerpointTemplateMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { PowerPointSettings } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useUploadPowerpointTemplateMutation,
  useRemovePowerpointTemplateMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { CapabilityPlatformPanelProps } from "../types";
import { CAPABILITY_ID } from "./api/pptBuilderCapabilityApi";
import { useGetPptBuilderBuiltinQuery, useGetPptBuilderAnalysisQuery } from "./api/pptBuilderCapabilityOpenApi";
import type { TemplateInventory } from "./api/pptBuilderCapabilityOpenApi";
import type { PreviewSource } from "./usePatternsPreview";
import { PatternReviewDialog } from "./PatternReviewDialog";
import { PptBuilderVisionSettings } from "./PptBuilderVisionSettings";
import { effectiveInventory, summarize, upsertOverride, readOverrides } from "./types";
import type { PatternOverride } from "./types";
import { TemplateGuideLink } from "./PptBuilderTemplatePanel";
import styles from "./PptBuilderTemplatePanel.module.css";

const POLL_MS = 3000;
const K = "capability.ppt_builder.platform";

export function PptBuilderPlatformPanel({
  canManage,
  organizationId,
  runtimeId,
  baseUrl,
}: CapabilityPlatformPanelProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const routedUrl = useSelector((state: { capabilityRouting: CapabilityRoutingState }) =>
    selectCapabilityBaseUrl(state, `${organizationId}/${runtimeId}/${CAPABILITY_ID}`),
  );
  const routed = Boolean(baseUrl && routedUrl === baseUrl);
  const target = { spaceId: organizationId, runtimeId };
  const query = useGetPowerpointSettingsQuery(target, {
    skip: !canManage || !runtimeId,
    pollingInterval: POLL_MS,
    refetchOnMountOrArgChange: true,
  });
  const platform = query.currentData;
  const reference = platform?.current.analysis_reference;
  const analysisQuery = useGetPptBuilderAnalysisQuery(
    { ...target, instanceId: reference ?? "" },
    { skip: !routed || !reference, refetchOnMountOrArgChange: true },
  );
  const current = analysisQuery.currentData ?? null;
  const builtinQuery = useGetPptBuilderBuiltinQuery(target, { skip: !routed || !platform || !!reference });
  const replacement = platform?.replacement;
  const [rerun, { isLoading: rerunning }] = useRerunPowerpointTemplateMutation();
  const [resetTemplate, { isLoading: resetting }] = useRemovePowerpointTemplateMutation();
  const [saveOverrides, { isLoading: saving }] = usePutPowerpointSettingsMutation();
  const [uploadTemplate, { isLoading: uploading }] = useUploadPowerpointTemplateMutation();
  const [confirmReset, setConfirmReset] = useState(false);
  const [review, setReview] = useState<{
    inventory: TemplateInventory;
    previewSource: PreviewSource;
    fileId?: string;
    overrides: PatternOverride[];
  } | null>(null);
  const [draft, setDraft] = useState<PatternOverride[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const savedOverrides = readOverrides((platform?.config ?? {}) as Record<string, unknown>);
  const inventory = reference ? current?.inventory : builtinQuery.currentData?.inventory;
  const effective = useMemo(
    () => (inventory ? effectiveInventory(inventory, draft ?? savedOverrides) : null),
    [inventory, draft, savedOverrides],
  );
  const summary = effective ? summarize(effective) : null;
  const busy = uploading || rerunning || resetting || saving;
  const hasTemplate = Boolean(platform?.current.file || replacement?.file);
  const expectedFileId = replacement?.file?.id ?? platform?.current.file?.id;
  const previewSource = reference
    ? current?.has_thumbnails
      ? { kind: "analysis" as const, instanceId: reference, spaceId: organizationId, baseUrl: baseUrl ?? undefined }
      : null
    : { kind: "builtin" as const, baseUrl: baseUrl ?? undefined };

  // Scoped polling refreshes settings independently of successful writes.
  const handlePick = async (file: File) => {
    try {
      await uploadTemplate({
        ...target,
        expectedFileId,
        "Idempotency-Key": crypto.randomUUID(),
        fileUpload: { file },
      }).unwrap();
      showSuccess({ summary: t(`${K}.uploaded`) });
    } catch (error) {
      showError({ summary: t(`${K}.uploadError`), detail: normalizeApiError(error).detail });
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };
  const handleRerun = async () => {
    try {
      await rerun({ ...target, powerPointChange: { expected_file_id: expectedFileId } }).unwrap();
      showSuccess({ summary: t(`${K}.rerunStarted`) });
    } catch (error) {
      showError({ summary: t(`${K}.rerunError`), detail: normalizeApiError(error).detail });
    }
  };
  const handleReset = async () => {
    setConfirmReset(false);
    try {
      await resetTemplate({ ...target, expectedFileId }).unwrap();
      showSuccess({ summary: t(`${K}.resetDone`) });
      setDraft(null);
    } catch (error) {
      showError({ summary: t(`${K}.resetError`), detail: normalizeApiError(error).detail });
    }
  };
  // Swift saves corrections when the slide review closes; a failure keeps the edits open.
  const handleReviewClose = async () => {
    if (saving) return;
    if (draft && JSON.stringify(draft) !== JSON.stringify(review?.overrides)) {
      try {
        await saveOverrides({
          ...target,
          powerPointSettingsChange: {
            expected_file_id: review?.fileId,
            config: { overrides: draft },
          },
        }).unwrap();
        showSuccess({ summary: t(`${K}.overridesSaved`) });
      } catch (error) {
        showError({ summary: t(`${K}.overridesError`), detail: normalizeApiError(error).detail });
        return;
      }
    }
    setReview(null);
    setDraft(null);
  };
  const handleDownload = async () => {
    if (!baseUrl || !reference) return;
    try {
      const stem = (platform?.current.file?.name ?? "template").replace(/\.pptx$/i, "");
      await downloadAuthed(
        `${baseUrl}/analysis/${encodeURIComponent(reference)}/patterns.pdf?space_id=${encodeURIComponent(organizationId)}`,
        `${stem}-slides.pdf`,
      );
    } catch (error) {
      showError({ summary: t(`${K}.pdfError`), detail: error instanceof Error ? error.message : String(error) });
    }
  };
  if (!canManage) return <p className={styles.status}>{t("rework.weaverAgents.errors.forbidden")}</p>;
  if (!baseUrl) return <p className={styles.status}>{t(`${K}.unavailable`)}</p>;
  if (query.isError && !platform)
    return (
      <p className={styles.error} role="alert">
        {t(`${K}.loadError`)}
      </p>
    );
  if (!platform)
    return (
      <p className={styles.status} role="status">
        <Spinner size={16} /> {t(`${K}.loading`)}
      </p>
    );

  return (
    <div className={styles.root}>
      <p className={styles.hint}>{t(`${K}.intro`, { runtimeId })}</p>

      <div className={`${styles.settingCard} ${styles.stacked}`}>
        <div className={styles.uploadRow}>
          <Chip
            label={
              platform.current.file
                ? t(`${K}.current`, { name: platform.current.file?.name ?? "" })
                : t(`${K}.fredTemplate`)
            }
            leading={<Icon category="outlined" type={platform.current.file ? "slideshow" : "palette"} />}
          />
          {canManage && (
            <>
              <input
                ref={fileInputRef}
                className={styles.fileInput}
                type="file"
                accept=".pptx"
                disabled={busy}
                aria-label={t(`${K}.uploadAria`)}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void handlePick(file);
                }}
              />
              <Button
                color="primary"
                variant="outlined"
                size="small"
                disabled={busy || !baseUrl}
                icon={{ category: "outlined", type: "upload" }}
                onClick={() => fileInputRef.current?.click()}
              >
                {t(hasTemplate ? `${K}.replace` : `${K}.upload`)}
              </Button>
            </>
          )}
        </div>

        <PlatformStatus platform={platform} uploading={uploading} />
        {current && !current.current && !replacement && <p className={styles.status}>{t(`${K}.outdated`)}</p>}
        {(query.isError || analysisQuery.isError || builtinQuery.isError) && (
          <p className={styles.error} role="alert">
            {t(`${K}.loadError`)}
          </p>
        )}

        {summary && (
          <div className={styles.summaryRow}>
            <p className={styles.summary}>
              {t("capability.ppt_builder.form.summary", { patterns: summary.patterns, excluded: summary.excluded })}
            </p>
            <div className={styles.uploadRow}>
              <Button
                color="on-surface"
                variant="text"
                size="small"
                icon={{ category: "outlined", type: "grid_view" }}
                onClick={() => {
                  if (inventory)
                    setReview({
                      inventory,
                      previewSource,
                      fileId: platform.current.file?.id,
                      overrides: savedOverrides,
                    });
                }}
              >
                {t("capability.ppt_builder.form.review")}
              </Button>
              {current?.has_thumbnails && (
                <Button
                  color="on-surface"
                  variant="text"
                  size="small"
                  icon={{ category: "outlined", type: "picture_as_pdf" }}
                  onClick={() => void handleDownload()}
                >
                  {t(`${K}.patternsPdf`)}
                </Button>
              )}
            </div>
          </div>
        )}
        <TemplateGuideLink />
      </div>

      {canManage && (
        <>
          <PptBuilderVisionSettings />
          {(hasTemplate || savedOverrides.length > 0) && (
            <div className={styles.uploadRow}>
              {hasTemplate && (
                <Button
                  color="on-surface"
                  variant="outlined"
                  size="small"
                  disabled={busy || replacement?.preparation_state === "pending"}
                  icon={{ category: "outlined", type: "refresh" }}
                  onClick={() => void handleRerun()}
                >
                  {t(`${K}.rerun`)}
                </Button>
              )}
              <Button
                color="error"
                variant="outlined"
                size="small"
                disabled={busy}
                onClick={() => setConfirmReset(true)}
              >
                {t(`${K}.reset`)}
              </Button>
            </div>
          )}
        </>
      )}

      {review && (
        <PatternReviewDialog
          open
          inventory={effectiveInventory(review.inventory, draft ?? review.overrides)}
          previewSource={review.previewSource}
          readOnly={!canManage || saving}
          onOverride={(patternId, patch) => setDraft(upsertOverride(draft ?? review.overrides, patternId, patch))}
          onClose={() => void handleReviewClose()}
        />
      )}

      <ConfirmationDialog
        open={confirmReset}
        title={t(`${K}.resetConfirm.title`)}
        message={t(`${K}.resetConfirm.message`)}
        confirmLabel={t(`${K}.resetConfirm.confirm`)}
        cancelLabel={t(`${K}.resetConfirm.cancel`)}
        criticalAction
        onConfirm={() => void handleReset()}
        onCancel={() => setConfirmReset(false)}
      />
    </div>
  );
}

/** The candidate never hides the effective template or its slide review. */
export function PlatformStatus({ platform, uploading }: { platform: PowerPointSettings; uploading: boolean }) {
  const { t } = useTranslation();
  const replacement = platform.replacement;
  const keeps = platform.current.file ? "keepCurrent" : "keepFred";
  const name = replacement?.file?.name ?? "";
  if (uploading || replacement?.preparation_state === "pending")
    return (
      <p className={styles.status} role="status">
        <Spinner size={16} /> {t(`${K}.analysing.${keeps}`, { name })}
      </p>
    );
  if (replacement?.preparation_state === "failed")
    return (
      <div className={styles.failure} role="alert">
        <p className={styles.error}>{t(`${K}.failed.${keeps}`, { name })}</p>
        {replacement.preparation_error && <p className={styles.error}>{replacement.preparation_error}</p>}
      </div>
    );
  return null;
}
