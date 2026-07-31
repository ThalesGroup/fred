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
import { describe, expect, it } from "vitest";
import PageHeader from "./PageHeader.tsx";

describe("PageHeader", () => {
  it("renders the title as an <h1> and omits the subtitle/actions blocks when not given", () => {
    const html = renderToStaticMarkup(<PageHeader title="Team usage" />);
    expect(html).toContain("<h1");
    expect(html).toContain("Team usage");
    expect(html).not.toContain("<p");
  });

  it("renders a subtitle as a <p> below the title when given", () => {
    const html = renderToStaticMarkup(<PageHeader title="Evaluations" subtitle="Versioned, reusable case sets." />);
    expect(html).toContain("Evaluations");
    expect(html).toContain("<p");
    expect(html).toContain("Versioned, reusable case sets.");
  });

  it("renders actions when given, omits the actions wrapper when not", () => {
    const withActions = renderToStaticMarkup(<PageHeader title="X" actions={<button>New</button>} />);
    expect(withActions).toContain("<button");
    expect(withActions).toContain("New");

    const withoutActions = renderToStaticMarkup(<PageHeader title="X" />);
    expect(withoutActions).not.toContain("<button");
  });
});
