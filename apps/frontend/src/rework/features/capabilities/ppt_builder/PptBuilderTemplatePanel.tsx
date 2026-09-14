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

// The one surface both the Advanced-view widget and the Simple-view pack
// options render for ppt_builder: an optional template upload, a one-line
// summary of what the analysis found, and a "review patterns" button that
// opens the correction dialog. Nothing here is mandatory — upload, read the
// summary, save is the nominal path.

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { PatternReviewDialog } from "./PatternReviewDialog";
import type { PptBuilderAnalysis } from "./usePptBuilderAnalysis";
import styles from "./PptBuilderTemplatePanel.module.css";

interface Props {
  disabled: boolean;
  analysis: PptBuilderAnalysis;
}

export function PptBuilderTemplatePanel({ disabled, analysis }: Props) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const {
    stagedFile,
    hasPersistedTemplate,
    isAnalyzing,
    analyzeFailed,
    errors,
    effective,
    droppedOverrides,
    summary,
    usesTheme,
    previewSource,
    updateOverride,
    blockingError,
    handlePick,
    handleClear: clearAnalysis,
  } = analysis;

  const handleClear = () => {
    clearAnalysis();
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const showReplaceLabel = hasPersistedTemplate || Boolean(stagedFile);

  return (
    <div className={styles.root}>
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
            if (file) void handlePick(file);
          }}
        />
        <Button
          color="primary"
          variant="outlined"
          size="small"
          disabled={disabled || isAnalyzing}
          icon={isAnalyzing ? undefined : { category: "outlined", type: "upload" }}
          onClick={() => fileInputRef.current?.click()}
        >
          {isAnalyzing ? (
            <span className={styles.buttonSpinner}>
              <Spinner size={16} />
            </span>
          ) : showReplaceLabel ? (
            t("capability.ppt_builder.form.replaceTemplate")
          ) : (
            t("capability.ppt_builder.form.uploadTemplate")
          )}
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
            label={t("capability.ppt_builder.form.builtInTheme")}
            leading={<Icon category="outlined" type="palette" />}
          />
        )}
      </div>

      {blockingError && <p className={styles.blocking}>{blockingError}</p>}
      {analyzeFailed && <p className={styles.error}>{t("capability.ppt_builder.form.analyzeFailed")}</p>}
      {errors.length > 0 && (
        <ul className={styles.errorList}>
          {errors.map((error, index) => (
            <li key={`${error.code}-${index}`} className={styles.error}>
              {t(`capability.ppt_builder.errors.${error.code}`, { defaultValue: error.message })}
            </li>
          ))}
        </ul>
      )}

      {droppedOverrides.length > 0 && (
        <p className={styles.summary}>
          {t("capability.ppt_builder.form.droppedOverrides", { count: droppedOverrides.length })}
        </p>
      )}

      {summary && effective && (
        <div className={styles.summaryRow}>
          <p className={styles.summary}>
            {t(usesTheme ? "capability.ppt_builder.form.summaryTheme" : "capability.ppt_builder.form.summary", {
              patterns: summary.patterns,
              fixed: summary.fixed,
              excluded: summary.excluded,
            })}
          </p>
          <Button
            color="on-surface"
            variant="text"
            size="small"
            disabled={disabled}
            icon={{ category: "outlined", type: "grid_view" }}
            onClick={() => setReviewOpen(true)}
          >
            {t("capability.ppt_builder.form.review")}
          </Button>
        </div>
      )}

      {reviewOpen && effective && (
        <PatternReviewDialog
          open={reviewOpen}
          inventory={effective}
          previewSource={previewSource}
          readOnly={usesTheme || disabled}
          onOverride={updateOverride}
          onClose={() => setReviewOpen(false)}
        />
      )}
    </div>
  );
}
