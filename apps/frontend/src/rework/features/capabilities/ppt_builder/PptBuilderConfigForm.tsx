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

// The ppt_builder agent-form widget, used by the Advanced capability card and
// the Simple "Generate a presentation" pack alike: it owns every config field.

import type { CapabilityConfigWidgetProps } from "../types";
import { useEffect } from "react";
import { PptBuilderTemplatePanel } from "./PptBuilderTemplatePanel";
import { USE_VISION_KEY } from "./types";
import { usePptBuilderAnalysis } from "./usePptBuilderAnalysis";
import { useVisionAvailability } from "./useVisionAvailability";

export type PptBuilderConfigFormProps = Pick<
  CapabilityConfigWidgetProps,
  "teamId" | "agentInstanceId" | "disabled" | "configValues" | "onConfigChange" | "assetFiles" | "onAssetFileChange"
>;

export function PptBuilderConfigForm({
  teamId,
  agentInstanceId,
  disabled,
  configValues,
  onConfigChange,
  assetFiles,
  onAssetFileChange,
}: PptBuilderConfigFormProps) {
  const analysis = usePptBuilderAnalysis({
    teamId,
    agentInstanceId,
    configValues,
    onConfigChange,
    assetFiles,
    onAssetFileChange,
  });
  const vision = useVisionAvailability();
  useEffect(() => {
    if (vision.available === false && configValues[USE_VISION_KEY] !== false) {
      onConfigChange(USE_VISION_KEY, false);
    }
  }, [vision.available, configValues, onConfigChange]);
  return (
    <PptBuilderTemplatePanel
      disabled={disabled}
      analysis={analysis}
      vision={vision}
      configValues={configValues}
      onConfigChange={onConfigChange}
    />
  );
}
