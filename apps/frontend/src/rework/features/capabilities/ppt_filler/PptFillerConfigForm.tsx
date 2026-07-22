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

// The ppt_filler agent-creation form widget (#1903, RFC §9 item 4): upload the
// .pptx template, run the capability's stateless /analyze route for INSTANT
// per-slide schema preview + slide-numbered errors, and gate Save while the
// mandatory template is missing or misconfigured. The uploaded file itself
// travels with the atomic save (multipart with-assets endpoints) — this
// preview never stores anything; the backend re-parses the real bytes on save.

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import type { CapabilityConfigWidgetProps } from "../types";
import {
  useAnalyzeAnalyzePostMutation,
  type BodyAnalyzeAnalyzePost,
  type ParseResult,
  type SlideSchema,
  type TemplateError,
} from "./api/pptFillerCapabilityOpenApi";
import styles from "./PptFillerConfigForm.module.css";

/** The manifest's one upload slot key (AssetSlot.key on the backend). */
const TEMPLATE_SLOT = "template";

/**
 * i18n an error by its stable code (the RFC contract: `code` is the machine
 * key, `message` the English fallback). Unknown codes fall back to the
 * backend-provided message so a new code never renders blank.
 */
function useTemplateErrorText() {
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

export function PptFillerConfigForm({
  disabled,
  configValues,
  assetFiles,
  onAssetFileChange,
  onBlockingErrorChange,
}: CapabilityConfigWidgetProps) {
  const { t } = useTranslation();
  const errorText = useTemplateErrorText();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
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
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

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
          disabled={disabled}
          icon={{ category: "outlined", type: "upload" }}
          onClick={() => fileInputRef.current?.click()}
        >
          {hasPersistedTemplate || stagedFile
            ? t("capability.ppt_filler.form.replaceTemplate")
            : t("capability.ppt_filler.form.uploadTemplate")}
        </Button>
        {stagedFile && (
          <span className={styles.fileName}>
            {stagedFile.name}
            <button
              type="button"
              className={styles.clearButton}
              onClick={handleClear}
              disabled={disabled}
              aria-label={t("capability.ppt_filler.form.clearAria")}
            >
              <Icon category="outlined" type="close" />
            </button>
          </span>
        )}
        {!stagedFile && hasPersistedTemplate && (
          <span className={styles.fileName}>{t("capability.ppt_filler.form.currentTemplate")}</span>
        )}
      </div>

      <Link className={styles.learnMoreLink} to="/ppt-filler-help" target="_blank" rel="noopener noreferrer">
        {t("capability.ppt_filler.form.learnMore")}
      </Link>

      {blockingError && <p className={styles.blocking}>{blockingError}</p>}
      {isAnalyzing && <p className={styles.hint}>{t("capability.ppt_filler.form.analyzing")}</p>}
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

      {previewSlides.length > 0 && (
        <div className={styles.schema}>
          <p className={styles.schemaTitle}>{t("capability.ppt_filler.form.schemaTitle")}</p>
          {previewSlides.map((slide) => (
            <div key={slide.slide} className={styles.slideGroup}>
              <p className={styles.slideTitle}>{t("capability.ppt_filler.form.slide", { number: slide.slide })}</p>
              <ul className={styles.keyList}>
                {(slide.keys ?? []).map((keyField) => (
                  <li key={keyField.key} className={styles.keyRow}>
                    <code className={styles.keyName}>{`{{${keyField.key}}}`}</code>
                    {keyField.type === "image" && (
                      <span className={styles.imageBadge}>
                        {t("capability.ppt_filler.form.imageBadge", { folder: keyField.folder ?? "" })}
                      </span>
                    )}
                    <span className={styles.keyDescription}>
                      {keyField.description || t("capability.ppt_filler.form.noDescription")}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
