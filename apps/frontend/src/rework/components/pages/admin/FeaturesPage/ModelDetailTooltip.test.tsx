// @vitest-environment happy-dom
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

import { act } from "react";
import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import { ModelDetailTooltip } from "./ModelDetailTooltip";

const mock = vi.hoisted(() => ({
  loadDetail: vi.fn(),
  detail: undefined as Record<string, unknown> | undefined,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/atoms/Tooltip/Tooltip.tsx", () => ({
  Tooltip: ({ children, content }: { children: ReactNode; content: ReactNode }) => (
    <div>
      {children}
      <div>{content}</div>
    </div>
  ),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useLazyModelDiscoveryDetailQuery: () => [mock.loadDetail, { data: mock.detail, isFetching: false, isError: false }],
}));

describe("ModelDetailTooltip", () => {
  const renderDetail = () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    act(() => root.render(<ModelDetailTooltip sourceId="mistral" modelId="mistral-large" runtimeId="pod-1" />));
    return {
      container,
      cleanup: () => {
        act(() => root.unmount());
        container.remove();
      },
    };
  };

  it("requests model detail only when the info icon is clicked", () => {
    mock.detail = undefined;
    mock.loadDetail.mockClear();
    const { container, cleanup } = renderDetail();
    expect(mock.loadDetail).not.toHaveBeenCalled();
    expect(container.querySelector("button .material-symbols-outlined")?.textContent).toBe("info");
    act(() => container.querySelector("button")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(mock.loadDetail).toHaveBeenCalledWith({ sourceId: "mistral", modelId: "mistral-large", runtimeId: "pod-1" });
    cleanup();
  });

  it("renders nested upstream fields as keys and values", () => {
    mock.detail = { id: "mistral-large", max_context_length: 262144, capabilities: { completion_chat: true } };
    const { container, cleanup } = renderDetail();
    expect(container.textContent).toContain("max_context_length");
    expect(container.textContent).toContain("262144");
    expect(container.textContent).toContain("completion_chat");
    expect(container.textContent).toContain("true");
    cleanup();
  });
});
