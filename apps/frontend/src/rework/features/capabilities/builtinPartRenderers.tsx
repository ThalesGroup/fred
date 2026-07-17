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

// Renderers for the frozen base `UiPart` kinds (link, geo) — the builtin half
// of the part-renderer registry (#1977). Capability kinds come from plugins.

import { useTranslation } from "react-i18next";
import type { GeoPart, LinkPart } from "../../../slices/runtime/runtimeOpenApi";
import Icon from "@shared/atoms/Icon/Icon";
import { ArtifactLinkChip } from "@shared/molecules/ArtifactLinks/ArtifactLinkChip";
import type { UiPartRenderer, UiPartRendererProps } from "./types";
import styles from "./builtinPartRenderers.module.css";

function LinkPartRenderer({ part }: UiPartRendererProps) {
  return <ArtifactLinkChip link={part as unknown as LinkPart} />;
}

/**
 * Minimal geo summary chip: no map library ships with the frontend today, so
 * the base `geo` kind renders a typed placeholder (feature count) instead of
 * being silently dropped, as it was before the registry existed.
 */
function GeoPartRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const geo = part as unknown as GeoPart;
  const features = Array.isArray(geo.geojson?.features) ? geo.geojson.features.length : 0;

  return (
    <span className={styles.geoChip} role="note" aria-label={t("chatbot.uiParts.geoAria")}>
      <span className={styles.geoIcon} aria-hidden>
        <Icon category="outlined" type="map" />
      </span>
      {t("chatbot.uiParts.geoSummary", { count: features })}
    </span>
  );
}

/** Registry seed for the frozen base kinds; plugin kinds must not collide. */
export const builtinPartRenderers: Record<string, UiPartRenderer> = {
  link: LinkPartRenderer,
  geo: GeoPartRenderer,
};
