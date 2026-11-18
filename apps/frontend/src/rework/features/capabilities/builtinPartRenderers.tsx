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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import "leaflet/dist/leaflet.css";
import type { GeoPart, LinkPart } from "../../../slices/runtime/runtimeOpenApi";
import Icon from "@shared/atoms/Icon/Icon";
import { ArtifactLinkChip } from "@shared/molecules/ArtifactLinks/ArtifactLinkChip";
import { CitationLinkChip } from "@shared/molecules/ArtifactLinks/CitationLinkChip";
import type { UiPartIdentity, UiPartRenderer, UiPartRendererProps } from "./types";
import styles from "./builtinPartRenderers.module.css";

// Citations open the third-party page directly; every other kind is a Fred file.
function LinkPartRenderer({ part }: UiPartRendererProps) {
  const link = part as unknown as LinkPart;
  return link.kind === "citation" ? <CitationLinkChip link={link} /> : <ArtifactLinkChip link={link} />;
}

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

/** Render a typed GeoPart with Leaflet's browser API. */
function GeoPartRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const geo = part as unknown as GeoPart;
  const features = Array.isArray(geo.geojson?.features) ? geo.geojson.features.length : 0;
  const container = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(false);
    let disposed = false;
    let map: import("leaflet").Map | undefined;

    async function mount() {
      if (!container.current) return;
      try {
        const L = await import("leaflet");
        if (disposed || !container.current) return;
        map = L.map(container.current, { scrollWheelZoom: false });
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(map);
        const layer = L.geoJSON(geo.geojson as Parameters<typeof L.geoJSON>[0], {
          pointToLayer: (_feature, latlng) => L.circleMarker(latlng, { radius: 7 }),
          style: (feature) => {
            const color = feature?.properties?.color;
            const fillOpacity = feature?.properties?.fillOpacity;
            return {
              color: typeof color === "string" && /^#[0-9a-fA-F]{3,8}$/.test(color) ? color : "#6366f1",
              fillOpacity: typeof fillOpacity === "number" && fillOpacity >= 0 && fillOpacity <= 1 ? fillOpacity : 0.3,
            };
          },
          onEachFeature: (feature, featureLayer) => {
            const label = feature.properties?.[geo.popup_property || "name"];
            if (typeof label === "string" || typeof label === "number") {
              const content = document.createElement("span");
              content.textContent = String(label);
              featureLayer.bindPopup(content);
            }
          },
        }).addTo(map);
        const bounds = layer.getBounds();
        if (bounds.isValid() && geo.fit_bounds !== false) map.fitBounds(bounds.pad(0.15), { maxZoom: 13 });
        else if (bounds.isValid()) map.setView(bounds.getCenter(), 10);
        else map.setView([0, 0], 2);
        setReady(true);
      } catch {
        map?.remove();
        map = undefined;
      }
    }

    void mount();
    return () => {
      disposed = true;
      map?.remove();
    };
  }, [geo.geojson, geo.fit_bounds, geo.popup_property]);

  return (
    <div className={styles.geoPanel}>
      {!ready && <GeoSummaryChip features={features} />}
      <div ref={container} className={styles.geoMap} role="region" aria-label={t("chatbot.uiParts.geoAria")} />
    </div>
  );
}

/**
 * A download chip is about its file: the same href twice in a message is one chip.
 * Other links, citations first, may legitimately repeat an href and are never merged.
 */
export const builtinPartIdentities: Record<string, UiPartIdentity> = {
  link: (part) => (part.kind === "download" && typeof part.href === "string" ? part.href : undefined),
};

/** Registry seed for the frozen base kinds; plugin kinds must not collide. */
export const builtinPartRenderers: Record<string, UiPartRenderer> = {
  link: LinkPartRenderer,
  geo: GeoPartRenderer,
};
