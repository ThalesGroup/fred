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

// Advanced-view upload for the optional .pptx brand template. Unlike ppt_filler's,
// there is nothing to parse client-side and no blocking error: just stage the file.

import { useRef } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import type { CapabilityConfigWidgetProps } from "../types";
import { usePptxGeneratorTemplate } from "./usePptxGeneratorTemplate";
import styles from "./PptxGeneratorConfigForm.module.css";

export function PptxGeneratorConfigForm({
  disabled,
  configValues,
  assetFiles,
  onAssetFileChange,
}: CapabilityConfigWidgetProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const {
    stagedFile,
    hasPersistedTemplate,
    handlePick,
    handleClear: clearTemplate,
  } = usePptxGeneratorTemplate({
    configValues,
    assetFiles,
    onAssetFileChange,
  });

  const handleClear = () => {
    clearTemplate();
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
          aria-label={t("capability.pptx_generator.form.uploadAria")}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) handlePick(file);
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
            ? t("capability.pptx_generator.form.replaceTemplate")
            : t("capability.pptx_generator.form.uploadTemplate")}
        </Button>
        {stagedFile && (
          <span className={styles.fileName}>
            {stagedFile.name}
            <button
              type="button"
              className={styles.clearButton}
              onClick={handleClear}
              disabled={disabled}
              aria-label={t("capability.pptx_generator.form.clearAria")}
            >
              <Icon category="outlined" type="close" />
            </button>
          </span>
        )}
        {!stagedFile && hasPersistedTemplate && (
          <span className={styles.fileName}>{t("capability.pptx_generator.form.currentTemplate")}</span>
        )}
      </div>
    </div>
  );
}
