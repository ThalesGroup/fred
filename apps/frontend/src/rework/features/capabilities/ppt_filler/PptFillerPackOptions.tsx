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

// The ppt_filler options shown INSIDE the "PowerPoint document" capability pack
// (Simple capabilities view, #2220 follow-up): the same mandatory-template upload
// as the Advanced-view widget, but trimmed to the pack's lighter surface — an
// upload button (spinner while analyzing), a removable file chip, the "how it
// works" link, the Save-gating template label and per-slide validation errors,
// plus a success toast once a freshly picked template analyzes cleanly. The
// upload/analyze/blocking logic is shared with PptFillerConfigForm via
// usePptTemplateAnalysis; the slide-schema preview is intentionally NOT shown here.

import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { usePptTemplateAnalysis } from "./usePptTemplateAnalysis";
import styles from "./PptFillerPackOptions.module.css";

interface PptFillerPackOptionsProps {
  disabled: boolean;
  configValues: Record<string, unknown>;
  assetFiles: Record<string, File | undefined>;
  onAssetFileChange: (slotKey: string, file: File | null) => void;
  onBlockingErrorChange: (message: string | null) => void;
}

export function PptFillerPackOptions({
  disabled,
  configValues,
  assetFiles,
  onAssetFileChange,
  onBlockingErrorChange,
}: PptFillerPackOptionsProps) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const {
    stagedFile,
    hasPersistedTemplate,
    isAnalyzing,
    analyzeFailed,
    previewErrors,
    blockingError,
    stagedAnalyzedClean,
    handlePick,
    handleClear: clearAnalysis,
    errorText,
  } = usePptTemplateAnalysis({ configValues, assetFiles, onAssetFileChange, onBlockingErrorChange });

  // One "upload succeeded" toast each time a freshly staged template analyzes
  // cleanly. `stagedAnalyzedClean` flips back to false on the next pick (analysis
  // is reset before re-analyzing), so a second good upload toasts again.
  useEffect(() => {
    if (stagedAnalyzedClean) {
      showSuccess({ summary: t("capability.ppt_filler.form.uploadSuccessToast") });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stagedAnalyzedClean]);

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
          aria-label={t("capability.ppt_filler.form.uploadAria")}
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
            t("capability.ppt_filler.form.replaceTemplate")
          ) : (
            t("capability.ppt_filler.form.uploadTemplate")
          )}
        </Button>

        {stagedFile ? (
          <Chip
            label={stagedFile.name}
            leading={<Icon category="outlined" type="slideshow" />}
            onRemove={handleClear}
            removeAriaLabel={t("capability.ppt_filler.form.clearAria")}
          />
        ) : (
          hasPersistedTemplate && (
            <Chip
              label={t("capability.ppt_filler.form.currentTemplate")}
              leading={<Icon category="outlined" type="check_circle" />}
            />
          )
        )}
      </div>

      <Link className={styles.learnMoreLink} to="/ppt-filler-help" target="_blank" rel="noopener noreferrer">
        {t("capability.ppt_filler.form.learnMore")}
      </Link>

      {blockingError && <p className={styles.blocking}>{blockingError}</p>}
      {analyzeFailed && <p className={styles.error}>{t("capability.ppt_filler.form.analyzeFailed")}</p>}

      {previewErrors.length > 0 && (
        <ul className={styles.errorList}>
          {previewErrors.map((error, index) => (
            <li key={`${error.slide}-${error.key}-${error.code}-${index}`} className={styles.error}>
              {errorText(error)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
