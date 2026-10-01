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

// The pptx_generator options shown INSIDE the "PowerPoint generation" capability
// pack (Simple capabilities view): an optional brand-template upload, trimmed to
// the pack's lighter surface — an upload button and a removable file chip.
// Unlike ppt_filler's mandatory template, there is nothing to analyze/validate
// client-side and no Save-gating error (PPTX-GENERATOR-CAPABILITY-RFC.md §4.2.1,
// §5) — upload/clear logic is shared with PptxGeneratorConfigForm via
// usePptxGeneratorTemplate.

import { useRef } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Icon from "@shared/atoms/Icon/Icon";
import { usePptxGeneratorTemplate } from "./usePptxGeneratorTemplate";
import styles from "./PptxGeneratorPackOptions.module.css";

interface PptxGeneratorPackOptionsProps {
  disabled: boolean;
  configValues: Record<string, unknown>;
  assetFiles: Record<string, File | undefined>;
  onAssetFileChange: (slotKey: string, file: File | null) => void;
}

export function PptxGeneratorPackOptions({
  disabled,
  configValues,
  assetFiles,
  onAssetFileChange,
}: PptxGeneratorPackOptionsProps) {
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
          {showReplaceLabel
            ? t("capability.pptx_generator.form.replaceTemplate")
            : t("capability.pptx_generator.form.uploadTemplate")}
        </Button>

        {stagedFile ? (
          <Chip
            label={stagedFile.name}
            leading={<Icon category="outlined" type="co_present" />}
            onRemove={handleClear}
            removeAriaLabel={t("capability.pptx_generator.form.clearAria")}
          />
        ) : (
          hasPersistedTemplate && (
            <Chip
              label={t("capability.pptx_generator.form.currentTemplate")}
              leading={<Icon category="outlined" type="check_circle" />}
            />
          )
        )}
      </div>
    </div>
  );
}
