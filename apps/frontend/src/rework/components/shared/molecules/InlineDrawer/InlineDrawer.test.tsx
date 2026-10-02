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

import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it } from "vitest";
import { InlineDrawer, type InlineDrawerProps } from "./InlineDrawer";

const props: InlineDrawerProps = {
  open: true,
  onClose: () => {},
  title: "Drawer",
  layout: "push",
  resizable: { persistKey: "width-test", maxViewportFraction: 0.8 },
};

afterEach(() => localStorage.clear());

it("keeps fractional pixel widths and prefers a persisted drag width", () => {
  expect(renderToStaticMarkup(<InlineDrawer {...props} width="480.5px" />)).toContain(
    "--drawer-width:min(480.5px, 80vw)",
  );
  localStorage.setItem("localHook:inline-drawer:width-test:width", "520");
  expect(renderToStaticMarkup(<InlineDrawer {...props} width="480.5px" />)).toContain(
    "--drawer-width:min(520px, 80vw)",
  );
});

it.each(["30rem", "50%", "30vw", "calc(100px + 20vw)"])(
  "rejects %s from untyped resizable consumers instead of silently treating it as pixels",
  (width) => {
    const untypedProps = { ...props, width } as InlineDrawerProps;
    expect(() => renderToStaticMarkup(<InlineDrawer {...untypedProps} />)).toThrow("resizable width must use pixels");
  },
);

it("keeps CSS widths available without resizing", () => {
  expect(renderToStaticMarkup(<InlineDrawer open onClose={() => {}} title="Overlay" width="30rem" />)).toContain(
    "--drawer-width:30rem",
  );
});
