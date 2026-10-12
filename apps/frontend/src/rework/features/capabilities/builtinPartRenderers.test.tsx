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
import { describe, expect, it, vi } from "vitest";
import { builtinPartRenderers } from "./builtinPartRenderers";
import type { UiPartRendererProps } from "./types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (value: string) => value }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));

const LinkRenderer = builtinPartRenderers.link;
const render = (part: Record<string, unknown>) =>
  renderToStaticMarkup(<LinkRenderer part={{ type: "link", ...part } as UiPartRendererProps["part"]} />);

describe("link part renderer", () => {
  it("renders a citation as a direct external anchor, never an authenticated download", () => {
    const html = render({ kind: "citation", href: "https://www.python.org/about", title: "About Python" });
    expect(html).toContain("<a ");
    expect(html).toContain('href="https://www.python.org/about"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("About Python");
    expect(html).not.toContain("<button");
  });

  it("drops citations whose URL is not http(s)", () => {
    expect(render({ kind: "citation", href: "javascript:alert(1)", title: "x" })).toBe("");
  });

  it("keeps Fred files as download buttons", () => {
    const html = render({ kind: "download", href: "/fs/download/a.pptx", file_name: "a.pptx" });
    expect(html).toContain("<button");
    expect(html).not.toContain("href=");
  });
});
