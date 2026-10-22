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

import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity.tsx";
import { toIconType } from "@shared/utils/Type.ts";
import { useTranslation } from "react-i18next";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { capabilityLabel } from "./capabilityEnablement";
import { ModelDisplayNameEditor } from "./ModelDisplayNameEditor";
import styles from "./FeaturesPage.module.css";

export function ModelIdentityCell({
  capability,
  dimmed,
  isNew = false,
}: {
  capability: CapabilityEnablementItem;
  dimmed: boolean;
  isNew?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className={styles.modelCell}>
      <div className={styles.modelIdentity}>
        <EntityIdentity
          name={capabilityLabel(t, capability)}
          icon={toIconType(capability.icon, "tune")}
          sourceId={capability.name}
          runtimeId={capability.runtime_id}
          version={capability.public_version}
          dimmed={dimmed}
        />
      </div>
      {isNew && <span className={styles.newModelBadge}>{t("rework.admin.capabilities.discovery.new")}</span>}
      {(capability.model_context_window_tokens ||
        capability.model_max_input_tokens ||
        capability.model_max_output_tokens) && (
        <span className={styles.modelSpecs}>
          {capability.model_context_window_tokens && (
            <span>
              {t("rework.admin.capabilities.modelSpecs.context", { count: capability.model_context_window_tokens })}
            </span>
          )}
          {capability.model_max_input_tokens && (
            <span>{t("rework.admin.capabilities.modelSpecs.input", { count: capability.model_max_input_tokens })}</span>
          )}
          {capability.model_max_output_tokens && (
            <span>
              {t("rework.admin.capabilities.modelSpecs.output", { count: capability.model_max_output_tokens })}
            </span>
          )}
        </span>
      )}
      <ModelDisplayNameEditor
        capabilityId={capability.id}
        wireName={capability.name}
        effectiveName={capability.model_display_name}
        overrideName={capability.model_display_name_override}
      />
    </div>
  );
}
