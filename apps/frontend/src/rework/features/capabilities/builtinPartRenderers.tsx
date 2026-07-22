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

import { lazy, Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { GeoPart, LinkPart } from "../../../slices/runtime/runtimeOpenApi";
import Icon from "@shared/atoms/Icon/Icon";
import { ArtifactLinkChip } from "@shared/molecules/ArtifactLinks/ArtifactLinkChip";
import type { UiPartRenderer, UiPartRendererProps } from "./types";
import styles from "./builtinPartRenderers.module.css";

function LinkPartRenderer({ part }: UiPartRendererProps) {
  return <ArtifactLinkChip link={part as unknown as LinkPart} />;
}

// `leaflet` touches `window`/`document` at module-load time (browser feature
// detection), which throws under the node-environment unit tests. Loading the
// map only via a dynamic import — gated behind a post-mount `ready` flag, never
// during the initial synchronous render — keeps it out of every eager import
// graph (tests, SSR) and off the main bundle until a `geo` part actually renders.
const LazyGeoMap = lazy(() => import("../../components/shared/molecules/GeoMap/GeoMap"));

function GeoSummaryChip({ features }: { features: number }) {
  const { t } = useTranslation();
  return (
    <span className={styles.geoChip} role="note" aria-label={t("chatbot.uiParts.geoAria")}>
      <span className={styles.geoIcon} aria-hidden>
        <Icon category="outlined" type="map" />
      </span>
      {t("chatbot.uiParts.geoSummary", { count: features })}
    </span>
  );
}

/**
 * Renders a `geo` part as an interactive Leaflet map. Mounts the map lazily
 * (see `LazyGeoMap`) and shows the feature-count chip as a synchronous first
 * paint / fallback while the map module loads.
 */
function GeoPartRenderer({ part }: UiPartRendererProps) {
  const geo = part as unknown as GeoPart;
  const features = Array.isArray(geo.geojson?.features) ? geo.geojson.features.length : 0;
  const [ready, setReady] = useState(false);

  useEffect(() => setReady(true), []);

  if (!ready) {
    return <GeoSummaryChip features={features} />;
  }

  return (
    <Suspense fallback={<GeoSummaryChip features={features} />}>
      <LazyGeoMap
        geojson={geo.geojson}
        popupProperty={geo.popup_property}
        fitBounds={geo.fit_bounds}
        style={geo.style}
      />
    </Suspense>
  );
}

/** Registry seed for the frozen base kinds; plugin kinds must not collide. */
export const builtinPartRenderers: Record<string, UiPartRenderer> = {
  link: LinkPartRenderer,
  geo: GeoPartRenderer,
};
