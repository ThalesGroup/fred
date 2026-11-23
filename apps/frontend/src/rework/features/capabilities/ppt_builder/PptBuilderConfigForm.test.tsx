// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ available: null as boolean | null, failed: false }));
vi.mock("./usePptBuilderAnalysis", () => ({ usePptBuilderAnalysis: () => ({}) }));
vi.mock("./useVisionAvailability", () => ({ useVisionAvailability: () => state }));
vi.mock("./PptBuilderTemplatePanel", () => ({ PptBuilderTemplatePanel: () => null }));

import { PptBuilderConfigForm } from "./PptBuilderConfigForm";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let cleanup: (() => void) | undefined;
afterEach(() => {
  cleanup?.();
  cleanup = undefined;
});

function renderForm(onConfigChange: (key: string, value: unknown) => void) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <PptBuilderConfigForm
        teamId="team"
        agentInstanceId="agent"
        disabled={false}
        configValues={{ use_vision: true }}
        onConfigChange={onConfigChange}
        assetFiles={{}}
        onAssetFileChange={vi.fn()}
      />,
    );
  });
  cleanup = () => {
    act(() => root.unmount());
    container.remove();
  };
}

it("preserves a saved vision choice when the availability request fails", () => {
  state.available = null;
  state.failed = true;
  const onConfigChange = vi.fn();
  renderForm(onConfigChange);
  expect(onConfigChange).not.toHaveBeenCalled();
});

it("switches to rules when Knowledge Flow confirms no vision model", () => {
  state.available = false;
  state.failed = false;
  const onConfigChange = vi.fn();
  renderForm(onConfigChange);
  expect(onConfigChange).toHaveBeenCalledWith("use_vision", false);
});
