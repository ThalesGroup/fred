import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import {
  PptFillerParams,
  SlideSchema,
  TemplateError,
  useAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostMutation,
  useListToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGetQuery,
} from "src/slices/agentic/agenticOpenApi";
import styles from "./PptFillerForm.module.css";

const PPT_FILLER_PROVIDER = "ppt_filler";

// Fallback accepted types, used only if the metadata endpoint hasn't resolved yet. The
// metadata endpoint is the source of truth (mirrors the backend asset processor).
const FALLBACK_ACCEPTED_TYPES = [".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"];

// Known parse-error codes mapped to i18n keys. Unmapped codes fall back to the server
// `message` (the English fallback the backend always provides).
const ERROR_CODE_I18N: Record<string, string> = {
  key_without_description: "agentTuning.fields.ppt_filler.errors.key_without_description",
  described_but_not_in_slide: "agentTuning.fields.ppt_filler.errors.described_but_not_in_slide",
};

/**
 * Reads a File as raw base64 (no `data:...;base64,` prefix), suitable for the backend's
 * transient `template_upload_b64` field.
 */
function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // FileReader.readAsDataURL yields "data:<mime>;base64,<payload>"; keep only payload.
      const commaIndex = result.indexOf(",");
      resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error("File read failed"));
    reader.readAsDataURL(file);
  });
}

/**
 * Returns true when `file` matches one of the accepted types — either by extension
 * (entries starting with ".") or by MIME type.
 */
function isAcceptedFile(file: File, acceptedTypes: string[]): boolean {
  const name = file.name.toLowerCase();
  return acceptedTypes.some((type) => {
    if (type.startsWith(".")) {
      return name.endsWith(type.toLowerCase());
    }
    return file.type === type;
  });
}

/**
 * Dedicated config form for the `ppt_filler` toolkit.
 *
 * Data flow: pick file → validate type → read base64 → call analyze (preview only) →
 * render per-slide schema + slide-numbered errors → persist `schema` + transient
 * `template_upload_b64` into params. The base64 bytes are attached ONLY when a file is
 * picked this session; ordinary edits leave the existing schema untouched and send no
 * bytes (the backend no-ops the template). The Save gate (mandatory template present) is
 * derived by the parent from the persisted `schema`/`template_upload_b64` in params.
 */
export function PptFillerForm({ params, onParamsChange }: ToolParamsProps<PptFillerParams>) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: metadata } = useListToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGetQuery();
  const acceptedTypes = metadata?.[PPT_FILLER_PROVIDER]?.accepted_file_types ?? FALLBACK_ACCEPTED_TYPES;

  const [analyze, { isLoading: isAnalyzing }] =
    useAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostMutation();

  // The schema preview reflects the persisted params (so editing an existing agent shows
  // its current template) and is refreshed after each analyze.
  const slides: SlideSchema[] = params.schema ?? [];
  const [errors, setErrors] = useState<TemplateError[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);

  // "Did the user pick a new file THIS session?" — drives whether bytes are sent on save
  // and whether we show "new file picked" vs "template already configured".
  const [pickedFileName, setPickedFileName] = useState<string | null>(null);

  const hasExistingTemplate = slides.length > 0;
  const hasNewUpload = Boolean(params.template_upload_b64);

  const handlePickClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Allow re-picking the same file later.
    e.target.value = "";
    if (!file) {
      return;
    }
    setLocalError(null);

    if (!isAcceptedFile(file, acceptedTypes)) {
      setLocalError(t("agentTuning.fields.ppt_filler.invalidFileType"));
      return;
    }

    try {
      const base64 = await readFileAsBase64(file);
      const result = await analyze({
        bodyAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePost: { file },
      }).unwrap();

      setErrors(result.errors ?? []);
      setPickedFileName(file.name);
      // Persist the analyzed schema for the preview AND attach the transient bytes so the
      // backend re-parses + stores the template on save. The backend strips the bytes
      // before persistence (it is the source of truth and recomputes the schema).
      onParamsChange({
        ...params,
        schema: result.schema ?? [],
        template_upload_b64: base64,
      });
    } catch {
      setLocalError(t("agentTuning.fields.ppt_filler.analyzeFailed"));
    }
  };

  return (
    <div className={styles.mainFormCard}>
      <div className={styles.fieldLabel}>
        <span>{t("agentTuning.fields.ppt_filler.title")}</span>
        <span className={styles.fieldDescription}>
          {t("agentTuning.fields.ppt_filler.description", { placeholder: "{{key}}" })}
        </span>
      </div>

      <div className={styles.uploadRow}>
        <button type="button" className={styles.uploadButton} onClick={handlePickClick} disabled={isAnalyzing}>
          {hasExistingTemplate || hasNewUpload
            ? t("agentTuning.fields.ppt_filler.replaceTemplate")
            : t("agentTuning.fields.ppt_filler.uploadTemplate")}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept={acceptedTypes.join(",")}
          onChange={handleFileChange}
          className={styles.hiddenInput}
        />

        {isAnalyzing && <span className={styles.statusAnalyzing}>{t("agentTuning.fields.ppt_filler.analyzing")}</span>}
        {!isAnalyzing && hasNewUpload && pickedFileName && (
          <span className={styles.statusConfigured}>
            {t("agentTuning.fields.ppt_filler.fileSelected", { fileName: pickedFileName })}
          </span>
        )}
        {!isAnalyzing && !hasNewUpload && hasExistingTemplate && (
          <span className={styles.statusConfigured}>{t("agentTuning.fields.ppt_filler.templateConfigured")}</span>
        )}
      </div>

      {localError && <span className={styles.localError}>{localError}</span>}

      {errors.length > 0 && (
        <div className={styles.errorList}>
          {errors.map((err, i) => (
            <div key={`${err.slide}-${err.key}-${i}`} className={styles.errorRow}>
              <span className={styles.errorSlide}>
                {t("agentTuning.fields.ppt_filler.errorOnSlide", { slide: err.slide })}
              </span>
              <span className={styles.errorMessage}>
                {ERROR_CODE_I18N[err.code]
                  ? t(ERROR_CODE_I18N[err.code], { key: `{{${err.key}}}`, slide: err.slide })
                  : err.message}
              </span>
            </div>
          ))}
        </div>
      )}

      {slides.length > 0 && (
        <div className={styles.slideList}>
          {slides.map((slide) => (
            <div key={slide.slide} className={styles.slideGroup}>
              <span className={styles.slideTitle}>
                {t("agentTuning.fields.ppt_filler.slideTitle", { slide: slide.slide })}
              </span>
              {(slide.keys ?? []).map((field) => (
                <div key={field.key} className={styles.keyRow}>
                  <span className={styles.keyName}>{field.key}</span>
                  {field.description && <span className={styles.keyDescription}>{field.description}</span>}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
