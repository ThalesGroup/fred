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

// Brand-template upload state shared by PptxGeneratorConfigForm (Advanced) and
// PptxGeneratorPackOptions (Simple). The slot is optional with nothing to parse
// client-side, so this is just staged-file/persisted-state plumbing.

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
