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

// Admin > Features drawer of "Generate a presentation": the platform default
// template agents without their own build on. A replacement is analysed while
// the current one stays in use; only capability managers see the write actions.

import { useEffect, useMemo, useRef, useState } from "react";
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
import type { CapabilityPlatformPanelProps } from "../types";
import { useCapabilityRouted } from "../useCapabilityRouted";
import { CAPABILITY_ID } from "./api/pptBuilderCapabilityApi";
import {
  useDeletePptBuilderPlatformTemplateMutation,
  useGetPptBuilderPlatformQuery,
  usePutPptBuilderPlatformOverridesMutation,
  useRerunPptBuilderPlatformAnalysisMutation,
  type AnalysisStatusResponse,
  type PlatformTemplateResponse,
} from "./api/pptBuilderCapabilityOpenApi";
import { PatternReviewDialog } from "./PatternReviewDialog";
import { PptBuilderVisionSettings } from "./PptBuilderVisionSettings";
import { effectiveInventory, LABELLING_MODEL_KEY, summarize, upsertOverride, USE_VISION_KEY } from "./types";
import type { PatternOverride } from "./types";
import { TemplateGuideLink } from "./PptBuilderTemplatePanel";
import { uploadPlatformTemplate } from "./uploadPlatformTemplate";
import { usePlatformVisionProfiles } from "./useVisionAvailability";
import styles from "./PptBuilderTemplatePanel.module.css";

const POLL_MS = 3000;
const K = "capability.ppt_builder.platform";

const inProgress = (analysis: AnalysisStatusResponse | null | undefined) =>
  analysis?.status === "pending" || analysis?.status === "running";

export function PptBuilderPlatformPanel({ canManage }: CapabilityPlatformPanelProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const routed = useCapabilityRouted(CAPABILITY_ID);
  const baseUrl = useSelector((state: { capabilityRouting: CapabilityRoutingState }) =>
    selectCapabilityBaseUrl(state, CAPABILITY_ID),
  );
  const [pollingInterval, setPollingInterval] = useState(0);
  const query = useGetPptBuilderPlatformQuery(undefined, { skip: !routed, pollingInterval });
  const platform: PlatformTemplateResponse | undefined = query.data;
  const current = platform?.analysis ?? null;
  const replacement = platform?.replacement ?? null;
  const analysing = inProgress(replacement) || current?.refreshing === true;
  useEffect(() => setPollingInterval(analysing ? POLL_MS : 0), [analysing]);

  const [rerun, { isLoading: rerunning }] = useRerunPptBuilderPlatformAnalysisMutation();
  const [resetTemplate, { isLoading: resetting }] = useDeletePptBuilderPlatformTemplateMutation();
  const [saveOverrides] = usePutPptBuilderPlatformOverridesMutation();
  const [uploading, setUploading] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [draft, setDraft] = useState<PatternOverride[] | null>(null);
  // The vision choice applies at the next upload or re-run; until edited, the stored one.
  const [visionDraft, setVisionDraft] = useState<Record<string, unknown> | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const visionProfiles = usePlatformVisionProfiles(!canManage);
  const visionValues = visionDraft ?? {
    [USE_VISION_KEY]: platform?.use_vision ?? true,
    [LABELLING_MODEL_KEY]: platform?.vision_profile_id ?? null,
  };
  const visionChoice = {
    use_vision: visionValues[USE_VISION_KEY] !== false,
    vision_profile_id: (visionValues[LABELLING_MODEL_KEY] as string | null) ?? null,
  };

  const savedOverrides = (platform?.overrides ?? []) as PatternOverride[];
  const effective = useMemo(
    () => (current?.inventory ? effectiveInventory(current.inventory, draft ?? savedOverrides) : null),
    [current, draft, savedOverrides],
  );
  const summary = effective ? summarize(effective) : null;
  const busy = uploading || rerunning || resetting;
  const hasTemplate = current !== null || replacement !== null;

  const handlePick = async (file: File) => {
    if (!baseUrl) return;
    setUploading(true);
    try {
      await uploadPlatformTemplate(baseUrl, file, visionChoice);
      showSuccess({ summary: t(`${K}.uploaded`) });
      setVisionDraft(null);
      void query.refetch();
    } catch (error) {
      showError({ summary: t(`${K}.uploadError`), detail: error instanceof Error ? error.message : String(error) });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleRerun = async () => {
    try {
      await rerun({ platformAnalysisRequest: visionChoice }).unwrap();
      showSuccess({ summary: t(`${K}.rerunStarted`) });
      setVisionDraft(null);
      void query.refetch();
    } catch (error) {
      showError({ summary: t(`${K}.rerunError`), detail: normalizeApiError(error).detail });
    }
  };

  const handleReset = async () => {
    setConfirmReset(false);
    try {
      await resetTemplate().unwrap();
      showSuccess({ summary: t(`${K}.resetDone`) });
      setVisionDraft(null);
      void query.refetch();
    } catch (error) {
      showError({ summary: t(`${K}.resetError`), detail: normalizeApiError(error).detail });
    }
  };

  // Edits are kept while the review is open and saved once, when it closes.
  const handleReviewClose = async () => {
    setReviewOpen(false);
    if (!draft || JSON.stringify(draft) === JSON.stringify(savedOverrides)) {
      setDraft(null);
      return;
    }
    try {
      await saveOverrides({ platformOverridesRequest: { overrides: draft } }).unwrap();
      showSuccess({ summary: t(`${K}.overridesSaved`) });
      void query.refetch();
    } catch (error) {
      showError({ summary: t(`${K}.overridesError`), detail: normalizeApiError(error).detail });
    } finally {
      setDraft(null);
    }
  };

  const handleDownload = async () => {
    if (!baseUrl) return;
    try {
      const stem = (platform?.template_filename ?? "template").replace(/\.pptx$/i, "");
      await downloadAuthed(`${baseUrl}/platform/patterns.pdf`, `${stem}-slides.pdf`);
    } catch (error) {
      showError({ summary: t(`${K}.pdfError`), detail: error instanceof Error ? error.message : String(error) });
    }
  };

  if (query.isError && !platform) return <p className={styles.error}>{t(`${K}.loadError`)}</p>;
  if (!platform) {
    return (
      <p className={styles.status} role="status">
        <Spinner size={16} /> {t(`${K}.loading`)}
      </p>
    );
  }

  return (
    <div className={styles.root}>
      <p className={styles.hint}>{t(`${K}.intro`)}</p>

      <div className={`${styles.settingCard} ${styles.stacked}`}>
        <div className={styles.uploadRow}>
          <Chip
            label={current ? t(`${K}.current`, { name: platform.template_filename ?? "" }) : t(`${K}.fredTemplate`)}
            leading={<Icon category="outlined" type={current ? "slideshow" : "palette"} />}
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
                onClick={() => setReviewOpen(true)}
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
          <PptBuilderVisionSettings
            disabled={busy}
            configValues={visionValues}
            onConfigChange={(key, value) => setVisionDraft({ ...visionValues, [key]: value })}
            vision={{ available: true, visionProfiles }}
            defaultModelLabel={t(`${K}.defaultModel`)}
          />
          {hasTemplate && (
            <div className={styles.uploadRow}>
              <Button
                color="on-surface"
                variant="outlined"
                size="small"
                disabled={busy || inProgress(replacement)}
                icon={{ category: "outlined", type: "refresh" }}
                onClick={() => void handleRerun()}
              >
                {t(`${K}.rerun`)}
              </Button>
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

      {reviewOpen && effective && (
        <PatternReviewDialog
          open={reviewOpen}
          inventory={effective}
          previewSource={current?.has_thumbnails ? { kind: "platform" } : null}
          readOnly={!canManage}
          onOverride={(patternId, patch) => setDraft(upsertOverride(draft ?? savedOverrides, patternId, patch))}
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

/** What happens to the platform template next; a replacement never stops the current one. */
export function PlatformStatus({ platform, uploading }: { platform: PlatformTemplateResponse; uploading: boolean }) {
  const { t } = useTranslation();
  const current = platform.analysis ?? null;
  const replacement = platform.replacement ?? null;
  const keeps = current ? "keepCurrent" : "keepFred";
  const name = platform.replacement_filename ?? "";

  if (uploading || inProgress(replacement)) {
    return (
      <p className={styles.status} role="status">
        <Spinner size={16} /> {t(`${K}.analysing.${keeps}`, { name })}
      </p>
    );
  }
  if (replacement) {
    return (
      <div className={styles.failure} role="alert">
        <p className={styles.error}>{t(`${K}.failed.${keeps}`, { name })}</p>
        {replacement.error && <p className={styles.error}>{replacement.error}</p>}
      </div>
    );
  }
  if (current?.refreshing) {
    return (
      <p className={styles.status} role="status">
        <Spinner size={16} /> {t(`${K}.refreshing`)}
      </p>
    );
  }
  if (current && !current.current) return <p className={styles.status}>{t(`${K}.outdated`)}</p>;
  return null;
}
