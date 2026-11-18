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
  const map = {
    fitBounds: vi.fn(),
    setView: vi.fn(),
    on: vi.fn(),
    getZoom: vi.fn(() => 9),
    getBounds: vi.fn(() => ({
      pad: vi.fn().mockReturnThis(),
      getWest: () => 5.7,
      getSouth: () => 42.9,
      getEast: () => 6.2,
      getNorth: () => 43.3,
      contains: () => true,
    })),
    createPane: vi.fn(() => ({ style: {} })),
    remove: vi.fn(),
    attributionControl: { addAttribution: vi.fn() },
  };
  const bounds = { isValid: () => true, pad: vi.fn().mockReturnThis() };
  const layer = {
    addTo: vi.fn().mockReturnThis(),
    addData: vi.fn().mockReturnThis(),
    clearLayers: vi.fn().mockReturnThis(),
    getBounds: () => bounds,
  };
  return {
    map,
    layer,
    createMap: vi.fn(() => map),
    tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
    imageOverlay: vi.fn(() => ({ addTo: vi.fn() })),
    geoJSON: vi.fn((_geojson?: unknown, _options?: unknown) => layer),
    circleMarker: vi.fn(),
    marker: vi.fn(),
    divIcon: vi.fn(),
    canvas: vi.fn(() => ({})),
  };
});

vi.mock("leaflet", () => ({
  map: leaflet.createMap,
  tileLayer: leaflet.tileLayer,
  imageOverlay: leaflet.imageOverlay,
  geoJSON: leaflet.geoJSON,
  circleMarker: leaflet.circleMarker,
  marker: leaflet.marker,
  divIcon: leaflet.divIcon,
  canvas: leaflet.canvas,
  CRS: { EPSG4326: { code: "EPSG:4326" } },
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
    features: [
      { type: "Feature", geometry: { type: "Point", coordinates: [2.3522, 48.8566] }, properties: { name: "Paris" } },
    ],
  };

  await act(async () => {
    root.render(<GeoRenderer part={{ type: "geo", geojson }} />);
  });

  await vi.waitFor(() => expect(leaflet.createMap).toHaveBeenCalledOnce());
  expect(leaflet.geoJSON).toHaveBeenCalledTimes(6);
  const world = leaflet.geoJSON.mock.calls[0]?.[0] as { features: unknown[] };
  expect(world.features).toHaveLength(258);
  expect(leaflet.tileLayer).not.toHaveBeenCalled();
  const roadsInView = leaflet.layer.addData.mock.calls[0]?.[0] as { features: unknown[] };
  expect(roadsInView.features.length).toBeGreaterThan(0);
  expect(roadsInView.features.length).toBeLessThan(100);
  expect(leaflet.imageOverlay).toHaveBeenCalledWith(
    expect.stringMatching(/^data:image\/webp;base64,/),
    [
      [-90, -180],
      [90, 180],
    ],
    expect.objectContaining({ interactive: false }),
  );
  expect(leaflet.createMap).toHaveBeenCalledWith(
    expect.any(HTMLElement),
    expect.objectContaining({ preferCanvas: true }),
  );
  expect(leaflet.canvas).toHaveBeenCalledWith({ pane: "geoUserPoints" });
  expect(leaflet.map.attributionControl.addAttribution).toHaveBeenCalledWith(expect.stringContaining("Natural Earth"));
  expect(leaflet.geoJSON).toHaveBeenCalledWith(geojson, expect.any(Object));
  const cityOptions = leaflet.geoJSON.mock.calls[4]?.[1] as {
    pointToLayer: (feature: { properties: { name: string } }, latlng: [number, number]) => unknown;
  };
  cityOptions.pointToLayer({ properties: { name: "<img>" } }, [43.12, 5.93]);
  expect(leaflet.marker).toHaveBeenCalledWith(
    [43.12, 5.93],
    expect.objectContaining({ interactive: false, keyboard: false }),
  );
  expect(leaflet.divIcon.mock.calls[leaflet.divIcon.mock.calls.length - 1]?.[0]?.html).toContain("&lt;img&gt;");
  expect(leaflet.map.fitBounds).toHaveBeenCalledWith(leaflet.layer.getBounds(), {
    padding: [24, 24],
    maxZoom: 13,
  });
  expect(host.textContent).not.toContain("FeatureCollection");
  expect(host.querySelector("ol li")?.textContent).toBe("Paris");
  expect(host.querySelector("details summary")?.textContent).toBe("chatbot.uiParts.geoLocations");
  expect(host.querySelector("details")?.open).toBe(false);
  expect(host.textContent).not.toContain("feature");
  expect(host.querySelector("[aria-busy]")?.getAttribute("aria-busy")).toBe("false");
  const [, options] = leaflet.geoJSON.mock.calls[5] as unknown as [
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

it("keeps feature text available if updated GeoJSON cannot be drawn", async () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  const GeoRenderer = builtinPartRenderers.geo;
  leaflet.geoJSON.mockImplementation((data: unknown) => {
    if ((data as { features?: { geometry?: unknown }[] } | undefined)?.features?.some((feature) => !feature.geometry)) {
      throw new Error("Invalid GeoJSON");
    }
    return leaflet.layer;
  });

  await act(async () => {
    root.render(<GeoRenderer part={{ type: "geo", geojson: { type: "FeatureCollection", features: [] } }} />);
  });
  await vi.waitFor(() => expect(host.querySelector("[aria-busy]")?.getAttribute("aria-busy")).toBe("false"));

  await act(async () => {
    root.render(<GeoRenderer part={{ type: "geo", geojson: { type: "FeatureCollection", features: [{}] } }} />);
  });
  await vi.waitFor(() => expect(host.querySelector("[aria-busy]")?.getAttribute("aria-busy")).toBe("false"));
  expect(host.querySelector("[role=status]")?.textContent).toBe("chatbot.uiParts.geoUnavailable");
  expect(host.querySelectorAll("ol li")).toHaveLength(1);
  expect(host.querySelector("details")?.open).toBe(true);

  await act(async () => root.unmount());
});
