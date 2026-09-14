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

// The ppt_builder agent-form widget (Advanced view): owns the `inventory` and
// `overrides` config fields through the shared template panel.

import type { CapabilityConfigWidgetProps } from "../types";
import { PptBuilderTemplatePanel } from "./PptBuilderTemplatePanel";
import { usePptBuilderAnalysis } from "./usePptBuilderAnalysis";

export function PptBuilderConfigForm({
  disabled,
  configValues,
  onConfigChange,
  assetFiles,
  onAssetFileChange,
  onBlockingErrorChange,
}: CapabilityConfigWidgetProps) {
  const analysis = usePptBuilderAnalysis({
    configValues,
    onConfigChange,
    assetFiles,
    onAssetFileChange,
    onBlockingErrorChange,
  });
  return <PptBuilderTemplatePanel disabled={disabled} analysis={analysis} />;
}
