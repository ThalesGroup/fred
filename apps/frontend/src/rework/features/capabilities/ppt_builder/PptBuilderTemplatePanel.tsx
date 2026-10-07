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

// The one surface both the Advanced widget and the Simple pack options render
// for ppt_builder: an optional template upload, the background analysis
// status, a summary with a "review patterns" entry, the vision and variety settings.
// Nothing here is mandatory.

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { PatternReviewDialog } from "./PatternReviewDialog";
import { PptBuilderVarietySettings } from "./PptBuilderVarietySettings";
import { PptBuilderVisionSettings } from "./PptBuilderVisionSettings";
import { isInProgress, type PptBuilderAnalysis } from "./usePptBuilderAnalysis";
import type { VisionAvailability } from "./useVisionAvailability";
import styles from "./PptBuilderTemplatePanel.module.css";

interface Props {
  disabled: boolean;
  analysis: PptBuilderAnalysis;
  vision: VisionAvailability;
  configValues: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
}

export function PptBuilderTemplatePanel({ disabled, analysis, vision, configValues, onConfigChange }: Props) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const { phase, stagedFile, hasPersistedTemplate, effective, summary } = analysis;
  const readOnlyReview = phase === "builtin" || disabled;

  const handleClear = () => {
    analysis.handleClear();
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className={styles.root}>
      <div className={`${styles.settingCard} ${styles.template}`}>
        <div className={styles.uploadRow}>
          <input
            ref={fileInputRef}
            className={styles.fileInput}
            type="file"
            accept=".pptx"
            disabled={disabled}
            aria-label={t("capability.ppt_builder.form.uploadAria")}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) analysis.handlePick(file);
            }}
          />
          <Button
            color="primary"
            variant="outlined"
            size="small"
            disabled={disabled}
            icon={{ category: "outlined", type: "upload" }}
            onClick={() => fileInputRef.current?.click()}
          >
            {hasPersistedTemplate || stagedFile
              ? t("capability.ppt_builder.form.replaceTemplate")
              : t("capability.ppt_builder.form.uploadTemplate")}
          </Button>
          {stagedFile ? (
            <Chip
              label={stagedFile.name}
              leading={<Icon category="outlined" type="slideshow" />}
              onRemove={handleClear}
              removeAriaLabel={t("capability.ppt_builder.form.clearAria")}
            />
          ) : hasPersistedTemplate ? (
            <Chip
              label={t("capability.ppt_builder.form.currentTemplate")}
              leading={<Icon category="outlined" type="check_circle" />}
            />
          ) : (
            <Chip
              label={t("capability.ppt_builder.form.builtInTemplate")}
              leading={<Icon category="outlined" type="palette" />}
            />
          )}
        </div>

        <AnalysisStatus analysis={analysis} disabled={disabled} />

        {analysis.droppedOverrides.length > 0 && (
          <p className={styles.summary}>
            {t("capability.ppt_builder.form.droppedOverrides", { count: analysis.droppedOverrides.length })}
          </p>
        )}

        {summary && effective && (
          <div className={styles.summaryRow}>
            <p className={styles.summary}>
              {t(
                phase === "builtin"
                  ? "capability.ppt_builder.form.summaryBuiltin"
                  : "capability.ppt_builder.form.summary",
                { patterns: summary.patterns, excluded: summary.excluded },
              )}
            </p>
            <Button
              color="on-surface"
              variant="text"
              size="small"
              icon={{ category: "outlined", type: "grid_view" }}
              onClick={() => setReviewOpen(true)}
            >
              {t("capability.ppt_builder.form.review")}
            </Button>
          </div>
        )}
      </div>

      <PptBuilderVisionSettings
        disabled={disabled}
        configValues={configValues}
        onConfigChange={onConfigChange}
        vision={vision}
      />

      <PptBuilderVarietySettings disabled={disabled} configValues={configValues} onConfigChange={onConfigChange} />

      {reviewOpen && effective && (
        <PatternReviewDialog
          open={reviewOpen}
          inventory={effective}
          previewSource={analysis.previewSource}
          readOnly={readOnlyReview}
          onOverride={analysis.updateOverride}
          onClose={() => setReviewOpen(false)}
        />
      )}
    </div>
  );
}

/** The line under the upload row: what happens to the template next. */
export function AnalysisStatus({ analysis, disabled }: { analysis: PptBuilderAnalysis; disabled: boolean }) {
  const { t } = useTranslation();
  const { phase } = analysis;

  if (phase === "staged") return <p className={styles.status}>{t("capability.ppt_builder.analysis.staged")}</p>;
  if (isInProgress(phase) || (phase === "unknown" && analysis.statusLoading)) {
    return (
      <p className={styles.status} role="status">
        <Spinner size={16} /> {t("capability.ppt_builder.analysis.inProgress")}
      </p>
    );
  }
  if (phase === "unknown") return <p className={styles.status}>{t("capability.ppt_builder.analysis.unknown")}</p>;
  if (phase === "succeeded" && !analysis.canRerun) return null;
  if (phase === "builtin") return null;

  const message =
    phase === "failed"
      ? t("capability.ppt_builder.analysis.failed")
      : phase === "interrupted"
        ? t("capability.ppt_builder.analysis.interrupted")
        : t("capability.ppt_builder.analysis.outdated");
  return (
    <div className={styles.failure} role={phase === "succeeded" ? undefined : "alert"}>
      <p className={phase === "succeeded" ? styles.status : styles.error}>{message}</p>
      {analysis.error && <p className={styles.error}>{analysis.error}</p>}
      {analysis.canRerun && (
        <Button
          color="primary"
          variant="outlined"
          size="small"
          disabled={disabled || analysis.isRerunning}
          icon={{ category: "outlined", type: "refresh" }}
          onClick={() => void analysis.rerun()}
        >
          {t("capability.ppt_builder.analysis.rerun")}
        </Button>
      )}
    </div>
  );
}
