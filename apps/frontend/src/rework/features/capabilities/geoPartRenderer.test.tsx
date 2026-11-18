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

// @vitest-environment happy-dom

import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, expect, it, vi } from "vitest";
import { builtinPartRenderers } from "./builtinPartRenderers";

const leaflet = vi.hoisted(() => {
  const map = { fitBounds: vi.fn(), setView: vi.fn(), remove: vi.fn() };
  const bounds = { isValid: () => true, pad: vi.fn().mockReturnThis() };
  const layer = { addTo: vi.fn().mockReturnThis(), getBounds: () => bounds };
  return {
    map,
    layer,
    createMap: vi.fn(() => map),
    tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
    geoJSON: vi.fn(() => layer),
    circleMarker: vi.fn(),
  };
});

vi.mock("leaflet", () => ({
  map: leaflet.createMap,
  tileLayer: leaflet.tileLayer,
  geoJSON: leaflet.geoJSON,
  circleMarker: leaflet.circleMarker,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

beforeEach(() => vi.clearAllMocks());

it("mounts a geo part as a Leaflet map and removes it on unmount", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const GeoRenderer = builtinPartRenderers.geo;
  const geojson = {
    type: "FeatureCollection",
    features: [{ type: "Feature", geometry: { type: "Point", coordinates: [2.3522, 48.8566] } }],
  };

  await act(async () => {
    root.render(<GeoRenderer part={{ type: "geo", geojson }} />);
  });

  expect(leaflet.createMap).toHaveBeenCalledOnce();
  expect(leaflet.geoJSON).toHaveBeenCalledWith(geojson, expect.any(Object));
  expect(leaflet.map.fitBounds).toHaveBeenCalledOnce();
  expect(host.textContent).not.toContain("FeatureCollection");
  const [, options] = leaflet.geoJSON.mock.calls[0] as unknown as [
    unknown,
    {
      onEachFeature: (
        feature: { properties: { name: string } },
        layer: { bindPopup: (content: HTMLElement) => void },
      ) => void;
    },
  ];
  const bindPopup = vi.fn();
  options.onEachFeature({ properties: { name: "<img src=x onerror=alert(1)>" } }, { bindPopup });
  expect(bindPopup.mock.calls[0][0].textContent).toBe("<img src=x onerror=alert(1)>");
  expect(bindPopup.mock.calls[0][0].innerHTML).toContain("&lt;img");

  await act(async () => root.unmount());
  expect(leaflet.map.remove).toHaveBeenCalledOnce();
  host.remove();
});

it("shows the summary again if updated GeoJSON cannot be drawn", async () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  const GeoRenderer = builtinPartRenderers.geo;
  leaflet.geoJSON
    .mockImplementationOnce(() => leaflet.layer)
    .mockImplementationOnce(() => {
      throw new Error("Invalid GeoJSON");
    });

  await act(async () => {
    root.render(<GeoRenderer part={{ type: "geo", geojson: { type: "FeatureCollection", features: [] } }} />);
  });
  expect(host.textContent).not.toContain("chatbot.uiParts.geoSummary");

  await act(async () => {
    root.render(<GeoRenderer part={{ type: "geo", geojson: { type: "FeatureCollection", features: [{}] } }} />);
  });
  expect(host.textContent).toContain("chatbot.uiParts.geoSummary");

  await act(async () => root.unmount());
});
