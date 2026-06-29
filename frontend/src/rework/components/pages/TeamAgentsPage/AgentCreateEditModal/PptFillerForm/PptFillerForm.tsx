import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import {
  PptFillerParams,
  SlideSchema,
  TemplateError,
  useListToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGetQuery,
} from "src/slices/agentic/agenticOpenApi";
// Use the enhanced analyze hook: it sends the template as multipart/form-data. The
// generated hook ships a plain-object body that gets JSON-stringified (File -> {}),
// which the backend rejects with 422. See agenticApiEnhancements.ts.
import { useAnalyzePptFillerTemplateMutation } from "src/slices/agentic/agenticApiEnhancements";
import styles from "./PptFillerForm.module.css";

const PPT_FILLER_PROVIDER = "ppt_filler";

// Fallback accepted types, used only if the metadata endpoint hasn't resolved yet. The
// metadata endpoint is the source of truth (mirrors the backend asset processor).
const FALLBACK_ACCEPTED_TYPES = [".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"];

// Known parse-error codes mapped to the i18n key of their group heading. Unmapped codes
// fall back to the server `message` (the English fallback the backend always provides).
const ERROR_CODE_HEADING_I18N: Record<string, string> = {
  key_without_description: "agentTuning.fields.ppt_filler.errors.key_without_description.heading",
  described_but_not_in_slide: "agentTuning.fields.ppt_filler.errors.described_but_not_in_slide.heading",
};

/**
 * Groups flat template errors first by error code, then by slide number, collecting the
 * affected keys. Turns a long repeated list into a compact "heading → slide → keys" tree.
 */
function groupErrors(errors: TemplateError[]) {
  const byCode = new Map<string, { code: string; message: string; slides: Map<number, string[]> }>();
  for (const err of errors) {
    let group = byCode.get(err.code);
    if (!group) {
      group = { code: err.code, message: err.message, slides: new Map() };
      byCode.set(err.code, group);
    }
    const keys = group.slides.get(err.slide) ?? [];
    keys.push(err.key);
    group.slides.set(err.slide, keys);
  }
  return [...byCode.values()].map((group) => ({
    code: group.code,
    message: group.message,
    slides: [...group.slides.entries()]
      .sort(([a], [b]) => a - b)
      .map(([slide, keys]) => ({ slide, keys })),
  }));
}

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

  const [analyze, { isLoading: isAnalyzing }] = useAnalyzePptFillerTemplateMutation();

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
        <Link
          className={styles.learnMoreLink}
          to="/ppt-filler-help"
          target="_blank"
          rel="noopener noreferrer"
        >
          {t("agentTuning.fields.ppt_filler.learnMore")}
        </Link>
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
          {groupErrors(errors).map((group) => (
            <div key={group.code} className={styles.errorGroup}>
              <span className={styles.errorHeading}>
                {ERROR_CODE_HEADING_I18N[group.code]
                  ? t(ERROR_CODE_HEADING_I18N[group.code])
                  : group.message}
              </span>
              {group.slides.map(({ slide, keys }) => (
                <div key={slide} className={styles.errorSlideGroup}>
                  <span className={styles.errorSlide}>
                    {t("agentTuning.fields.ppt_filler.slideTitle", { slide })}
                  </span>
                  <ul className={styles.errorKeyList}>
                    {keys.map((key) => (
                      <li key={key} className={styles.errorKey}>{`{{${key}}}`}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {errors.length === 0 && slides.length > 0 && (
        <div className={styles.validTemplate}>
          <span className={styles.validCheck} aria-hidden="true">
            ✓
          </span>
          <span>{t("agentTuning.fields.ppt_filler.validTemplate")}</span>
        </div>
      )}
    </div>
  );
}
