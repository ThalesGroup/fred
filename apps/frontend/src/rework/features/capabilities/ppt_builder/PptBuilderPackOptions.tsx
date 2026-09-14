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

// The ppt_builder options inside the "Presentation builder" pack (Simple
// capabilities view): the same panel as the Advanced widget — the template is
// optional, so there is nothing to trim.

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { PptBuilderTemplatePanel } from "./PptBuilderTemplatePanel";
import { usePptBuilderAnalysis } from "./usePptBuilderAnalysis";

interface Props {
  disabled: boolean;
  configValues: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
  assetFiles: Record<string, File | undefined>;
  onAssetFileChange: (slotKey: string, file: File | null) => void;
  onBlockingErrorChange: (message: string | null) => void;
}

export function PptBuilderPackOptions(props: Props) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const analysis = usePptBuilderAnalysis(props);
  const stagedClean = Boolean(analysis.stagedFile) && analysis.inventory !== null && analysis.errors.length === 0;

  // One toast per freshly staged template that analyses cleanly.
  useEffect(() => {
    if (stagedClean) showSuccess({ summary: t("capability.ppt_builder.form.uploadSuccessToast") });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stagedClean]);

  return <PptBuilderTemplatePanel disabled={props.disabled} analysis={analysis} />;
}
