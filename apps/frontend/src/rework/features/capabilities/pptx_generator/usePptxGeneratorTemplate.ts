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

// Shared pptx_generator brand-template upload state, consumed by BOTH the
// Advanced-view config widget (PptxGeneratorConfigForm) and the Simple-view
// capability pack options (PptxGeneratorPackOptions). Unlike ppt_filler's
// mandatory template, this slot is optional (RFC PPTX-GENERATOR-CAPABILITY §4.2.1)
// and there is nothing to parse/preview client-side, so this hook is just the
// staged-file/persisted-state plumbing — no analyze call, no blocking error.

/** The manifest's one upload slot key (AssetSlot.key on the backend). */
export const BRAND_TEMPLATE_SLOT = "brand_template";

interface UsePptxGeneratorTemplateArgs {
  configValues: Record<string, unknown>;
  assetFiles: Record<string, File | undefined>;
  onAssetFileChange: (slotKey: string, file: File | null) => void;
}

export interface PptxGeneratorTemplate {
  stagedFile: File | undefined;
  /** A brand template was uploaded and saved on a previous edit. */
  hasPersistedTemplate: boolean;
  handlePick: (file: File) => void;
  handleClear: () => void;
}

export function usePptxGeneratorTemplate({
  configValues,
  assetFiles,
  onAssetFileChange,
}: UsePptxGeneratorTemplateArgs): PptxGeneratorTemplate {
  const stagedFile = assetFiles[BRAND_TEMPLATE_SLOT];
  const hasPersistedTemplate = Boolean(configValues.template_key);

  return {
    stagedFile,
    hasPersistedTemplate,
    handlePick: (file: File) => onAssetFileChange(BRAND_TEMPLATE_SLOT, file),
    handleClear: () => onAssetFileChange(BRAND_TEMPLATE_SLOT, null),
  };
}
