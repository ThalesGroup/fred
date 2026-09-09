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

import { describe, expect, it } from "vitest";
import type { WikiPageDetail } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { rulesDraft } from "./rulesDraft";

const TEMPLATE = "## Vocabulary\n";

const detail = (over: Partial<WikiPageDetail>): WikiPageDetail => ({
  page: { page_id: "", slug: "rules", title: "Rules", kind: "rules" },
  content_md: "",
  revision_id: null,
  ...over,
});

describe("rulesDraft", () => {
  it("offers the template before the team has ever saved the page", () => {
    expect(rulesDraft(detail({}), TEMPLATE)).toBe(TEMPLATE);
  });

  it("leaves what the team wrote alone", () => {
    expect(rulesDraft(detail({ revision_id: "r1", content_md: "our rules" }), TEMPLATE)).toBe("our rules");
  });

  it("does not put the template back on a page the team emptied on purpose", () => {
    expect(rulesDraft(detail({ revision_id: "r1", content_md: "" }), TEMPLATE)).toBe("");
  });
});
