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
import { builtinPartRenderers } from "../builtinPartRenderers";

const leaflet = vi.hoisted(() => {
  const map = {
    fitBounds: vi.fn(),
    setView: vi.fn(),
    on: vi.fn(),
    getZoom: vi.fn(() => 9),
    getCenter: vi.fn(() => ({ lat: 43.12, lng: 5.93 })),
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
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [2.3522, 48.8566] },
        properties: { name: "Paris", description: "Capital of France" },
      },
    ],
  };

  await act(async () => {
    root.render(<GeoRenderer part={{ type: "geo", geojson, popup_property: "description" }} />);
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
    expect.objectContaining({ preferCanvas: true, scrollWheelZoom: true, zoomAnimation: false }),
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
  expect(host.querySelector("ol > li")?.firstChild?.textContent).toBe("Paris");
  expect(host.querySelector("ol li ul li")?.textContent).toBe("Capital of France");
  expect(host.querySelector("details summary")?.textContent).toBe("chatbot.uiParts.geoLocations");
  expect(host.querySelector("details")?.open).toBe(false);
  expect(host.textContent).not.toContain("feature");
  expect(host.querySelector("[aria-busy]")?.getAttribute("aria-busy")).toBe("false");
  const [, options] = leaflet.geoJSON.mock.calls[5] as unknown as [
    unknown,
    {
      onEachFeature: (
        feature: {
          geometry: { type: "Point"; coordinates: number[] };
          properties: { name: string; description?: string };
        },
        layer: {
          bindPopup: (content: HTMLElement) => void;
          bindTooltip: (content: HTMLElement, options: unknown) => void;
          on: (event: string, handler: () => void) => void;
          setTooltipContent: (content: HTMLElement | string) => void;
        },
      ) => void;
    },
  ];
  const bindPopup = vi.fn();
  const bindTooltip = vi.fn();
  const on = vi.fn();
  const setTooltipContent = vi.fn();
  options.onEachFeature(
    {
      geometry: { type: "Point", coordinates: [1, 1] },
      properties: { name: "<img src=x onerror=alert(1)>", description: "<script>alert(1)</script>" },
    },
    { bindPopup, bindTooltip, on, setTooltipContent },
  );
  expect(bindPopup.mock.calls[0][0].textContent).toBe("<img src=x onerror=alert(1)><script>alert(1)</script>");
  expect(bindPopup.mock.calls[0][0].innerHTML).toContain("&lt;img");
  expect(bindPopup.mock.calls[0][0].innerHTML).toContain("&lt;script&gt;");
  expect(bindTooltip).toHaveBeenCalledWith(
    expect.any(HTMLElement),
    expect.objectContaining({ permanent: true, interactive: false }),
  );
  expect(bindTooltip.mock.calls[0][0].textContent).toBe("<img src=x onerror=alert(1)>");
  expect(bindTooltip.mock.calls[0][0].innerHTML).toContain("&lt;img");
  const hover = on.mock.calls.find(([event]) => event === "mouseover")?.[1];
  hover();
  expect(setTooltipContent.mock.calls[0][0].textContent).toContain("<script>alert(1)</script>");
  expect(setTooltipContent.mock.calls[0][0].innerHTML).toContain("&lt;script&gt;");
  const unhover = on.mock.calls.find(([event]) => event === "mouseout")?.[1];
  unhover();
  expect(setTooltipContent.mock.calls[1][0].textContent).toBe("<img src=x onerror=alert(1)>");
  expect(setTooltipContent.mock.calls[1][0].innerHTML).toContain("&lt;img");

  const secondPopup = vi.fn();
  const secondTooltip = vi.fn();
  const secondOn = vi.fn();
  const secondSetTooltipContent = vi.fn();
  const longDescription = "A".repeat(300);
  options.onEachFeature(
    {
      geometry: { type: "Point", coordinates: [2.3522, 48.8566] },
      properties: { name: "Toulon", description: longDescription },
    },
    { bindPopup: secondPopup, bindTooltip: secondTooltip, on: secondOn, setTooltipContent: secondSetTooltipContent },
  );
  expect(secondPopup.mock.calls[0][0].textContent).toContain(longDescription);
  expect(secondTooltip).toHaveBeenCalledOnce();
  expect(secondTooltip.mock.calls[0][0].textContent).toBe("Toulon");
  const secondHover = secondOn.mock.calls.find(([event]) => event === "mouseover")?.[1];
  secondHover();
  expect(secondSetTooltipContent.mock.calls[0][0].textContent.length).toBeLessThan(150);

  const plainLayer = {
    bindPopup: vi.fn(),
    bindTooltip: vi.fn(),
    on: vi.fn(),
    setTooltipContent: vi.fn(),
  };
  options.onEachFeature(
    { geometry: { type: "Point", coordinates: [5.928, 43.1242] }, properties: { name: "Toulon" } },
    plainLayer,
  );
  expect(plainLayer.bindTooltip.mock.calls[0][0].textContent).toBe("Toulon");
  plainLayer.on.mock.calls.find(([event]) => event === "mouseover")?.[1]();
  expect(plainLayer.setTooltipContent.mock.calls[0][0].textContent).toBe("Toulonlat: 43.1242°, lon 5.9280°");
  plainLayer.on.mock.calls.find(([event]) => event === "mouseout")?.[1]();
  expect(plainLayer.setTooltipContent.mock.calls[1][0].textContent).toBe("Toulon");

  const duplicateTooltip = vi.fn();
  options.onEachFeature(
    {
      geometry: { type: "Point", coordinates: [2.3522, 48.8566] },
      properties: { name: "Also Toulon", description: "Same location" },
    },
    { bindPopup: vi.fn(), bindTooltip: duplicateTooltip, on: vi.fn(), setTooltipContent: vi.fn() },
  );
  expect(duplicateTooltip).not.toHaveBeenCalled();

  await act(async () => root.unmount());
  expect(leaflet.map.remove).toHaveBeenCalledOnce();
  host.remove();
});

it("enlarges the map in Fred's dialog and restores the current view", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const GeoRenderer = builtinPartRenderers.geo;
  const geojson = {
    type: "FeatureCollection",
    features: [
      { type: "Feature", geometry: { type: "Point", coordinates: [5.93, 43.12] }, properties: { name: "Toulon" } },
    ],
  };

  await act(async () => root.render(<GeoRenderer part={{ type: "geo", geojson }} />));
  const enlarge = host.querySelector<HTMLButtonElement>('button[aria-label="chatbot.uiParts.geoEnlarge"]');
  expect(enlarge).not.toBeNull();
  await act(async () => enlarge?.click());

  const dialog = document.querySelector<HTMLElement>('[role="dialog"][aria-modal="true"]');
  const titleId = dialog?.getAttribute("aria-labelledby");
  expect(document.getElementById(titleId ?? "")?.textContent).toBe("chatbot.uiParts.geoAria");
  expect(dialog?.querySelector('[aria-label="chatbot.uiParts.geoAria"]')).not.toBeNull();
  expect(dialog?.textContent).toContain("Toulon");
  expect(leaflet.createMap).toHaveBeenCalledTimes(2);
  expect(leaflet.map.setView).toHaveBeenCalledWith(leaflet.map.getCenter(), 9);
  expect(leaflet.map.remove).toHaveBeenCalledTimes(1);

  const close = [...(dialog?.querySelectorAll<HTMLButtonElement>("button") ?? [])].find(
    (button) => button.textContent === "chatbot.uiParts.geoClose",
  );
  close?.focus();
  const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
  await act(async () => window.dispatchEvent(tab));
  expect(tab.defaultPrevented).toBe(true);
  expect(dialog?.contains(document.activeElement)).toBe(true);
  await act(async () => close?.click());
  expect(document.querySelector('[role="dialog"][aria-modal="true"]')).toBeNull();
  expect(leaflet.createMap).toHaveBeenCalledTimes(3);
  expect(leaflet.map.remove).toHaveBeenCalledTimes(2);
  expect(document.activeElement).toBe(enlarge);

  await act(async () => root.unmount());
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
