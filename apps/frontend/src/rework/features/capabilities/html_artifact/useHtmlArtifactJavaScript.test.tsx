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
  refetch?: () => { unwrap: () => Promise<unknown> };
};
let freshAnswer = true;
let freshError = false;
const freshRead = vi.fn(() => ({
  unwrap: async () => {
    if (freshError) throw new Error("unavailable");
    return { settings: { allow_javascript: freshAnswer } };
  },
}));

vi.mock("../../../../hooks/useSelectedTeam", () => ({ useSelectedTeam: () => ({ teamId }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useTeamCapabilitySettingsQuery: () => query,
  useLazyTeamCapabilitySettingsQuery: () => [freshRead],
}));

const { useCheckHtmlArtifactJavaScriptAllowed, useHtmlArtifactJavaScriptAllowed } = await import(
  "./useHtmlArtifactJavaScript"
);

function Probe({ displayKey = "" }: { displayKey?: string }) {
  return <span>{String(useHtmlArtifactJavaScriptAllowed(displayKey))}</span>;
}

let checkNow: () => Promise<boolean>;
function CheckProbe() {
  checkNow = useCheckHtmlArtifactJavaScriptAllowed();
  return null;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  teamId = "team-a";
  freshAnswer = true;
  freshError = false;
  freshRead.mockClear();
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
  const render = (displayKey = "") => act(() => root.render(<Probe displayKey={displayKey} />));

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

  it("requires a fresh read before showing another artifact in an open pane", async () => {
    const pending: Array<(value: unknown) => void> = [];
    query.refetch = () => ({ unwrap: () => new Promise((resolve) => pending.push(resolve)) });

    render("artifact-a:v1");
    expect(container.textContent).toBe("false");
    await act(async () => pending.shift()!({ settings: { allow_javascript: true } }));
    expect(container.textContent).toBe("true");

    render("artifact-b:v1");
    expect(container.textContent).toBe("false");
    await act(async () => pending.shift()!({ settings: { allow_javascript: false } }));
    expect(container.textContent).toBe("false");
  });

  it("forces a new read for an HTML export and denies errors", async () => {
    act(() => root.render(<CheckProbe />));
    freshAnswer = false;

    expect(await checkNow()).toBe(false);
    expect(freshRead).toHaveBeenCalledWith({ teamId: "team-a", capabilityId: "html_artifact" }, false);

    freshError = true;
    expect(await checkNow()).toBe(false);
    teamId = undefined;
    act(() => root.render(<CheckProbe />));
    expect(await checkNow()).toBe(false);
    expect(freshRead).toHaveBeenCalledTimes(2);
  });
});
