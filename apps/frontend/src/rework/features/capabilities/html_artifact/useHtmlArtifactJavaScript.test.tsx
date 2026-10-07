// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let teamId: string | undefined;
let query: {
  data?: { settings: { allow_javascript: boolean } };
  currentData?: { settings: { allow_javascript: boolean } };
  isFetching: boolean;
  isError: boolean;
};

vi.mock("../../../../hooks/useSelectedTeam", () => ({ useSelectedTeam: () => ({ teamId }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useTeamCapabilitySettingsQuery: () => query,
}));

const { useHtmlArtifactJavaScriptAllowed } = await import("./useHtmlArtifactJavaScript");

function Probe() {
  return <span>{String(useHtmlArtifactJavaScriptAllowed())}</span>;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  teamId = "team-a";
  query = { currentData: { settings: { allow_javascript: true } }, isFetching: false, isError: false };
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("HTML artifact JavaScript posture", () => {
  const render = () => act(() => root.render(<Probe />));

  it("denies cached grants during a same-team refetch and after its failure", () => {
    render();
    expect(container.textContent).toBe("true");

    query = { currentData: { settings: { allow_javascript: true } }, isFetching: true, isError: false };
    render();
    expect(container.textContent).toBe("false");

    query = { currentData: { settings: { allow_javascript: true } }, isFetching: false, isError: true };
    render();
    expect(container.textContent).toBe("false");
  });

  it("denies the previous team's grant while switching teams or losing identity", () => {
    render();
    expect(container.textContent).toBe("true");

    teamId = "team-b";
    query = { data: { settings: { allow_javascript: true } }, isFetching: true, isError: false };
    render();
    expect(container.textContent).toBe("false");

    teamId = undefined;
    query = { data: { settings: { allow_javascript: true } }, isFetching: false, isError: false };
    render();
    expect(container.textContent).toBe("false");
  });
});
