// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { InlineDrawer } from "./InlineDrawer";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

it("sizes an opening on the parent width plus what onOpening frees", () => {
  localStorage.clear();
  window.innerWidth = 4000;
  const parent = document.createElement("div");
  Object.defineProperty(parent, "clientWidth", { value: 1000 });
  document.body.appendChild(parent);
  const root = createRoot(parent);
  const onOpening = vi.fn(() => 254);

  act(() =>
    root.render(
      <InlineDrawer
        open
        onClose={() => {}}
        title="Viewer"
        layout="push"
        resizable={{ persistKey: "test-drawer", openFraction: 0.5, maxViewportFraction: 1, onOpening }}
      >
        content
      </InlineDrawer>,
    ),
  );

  expect(onOpening).toHaveBeenCalledWith(1000);
  expect(parent.innerHTML).toContain("627px");
  act(() => root.unmount());
  parent.remove();
});
