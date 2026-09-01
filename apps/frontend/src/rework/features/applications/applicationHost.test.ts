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
import type { ApplicationSummary } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { applicationFrameTarget, parseApplicationFrameMessage } from "./applicationHost.ts";

function summary(uiPrefix: string): ApplicationSummary {
  return {
    id: "example",
    version: "1.0.0",
    name: { en: "Example" },
    description: { en: "Example application" },
    icon: "widgets",
    ui_prefix: uiPrefix,
  };
}

describe("applicationFrameTarget", () => {
  it("resolves a configured path against the Fred origin", () => {
    expect(applicationFrameTarget(summary("/apps/example-ui/"), "https://fred.example")).toEqual({
      src: "https://fred.example/apps/example-ui/",
      targetOrigin: "https://fred.example",
    });
  });

  it("keeps an absolute prefix on its own origin so the frame can move off Fred's", () => {
    expect(applicationFrameTarget(summary("https://apps.example/example/"), "https://fred.example")).toEqual({
      src: "https://apps.example/example/",
      targetOrigin: "https://apps.example",
    });
  });

  it.each(["javascript:alert(1)", "data:text/html,<script></script>", "file:///etc/passwd", ""])(
    "refuses %s as a frame source",
    (uiPrefix) => {
      expect(applicationFrameTarget(summary(uiPrefix), "https://fred.example")).toBeNull();
    },
  );
});

describe("parseApplicationFrameMessage", () => {
  it("accepts the announced protocol version", () => {
    expect(parseApplicationFrameMessage({ type: "fred:ready", protocolVersion: "1" })).toEqual({
      type: "fred:ready",
      protocolVersion: "1",
    });
  });

  it("normalizes an optional navigate flag", () => {
    expect(parseApplicationFrameMessage({ type: "fred:navigate", path: "reports/7" })).toEqual({
      type: "fred:navigate",
      path: "reports/7",
      replace: false,
    });
  });

  it("defaults a request's method, headers and body", () => {
    expect(parseApplicationFrameMessage({ type: "fred:request", requestId: "r1", path: "items" })).toEqual({
      type: "fred:request",
      requestId: "r1",
      path: "items",
      method: "GET",
      headers: {},
      body: null,
    });
  });

  it.each([
    ["a non-object payload", "fred:ready"],
    ["null", null],
    ["an array", [{ type: "fred:ready", protocolVersion: "1" }]],
    ["an unknown type", { type: "fred:teleport" }],
    ["a ready without a version", { type: "fred:ready" }],
    ["a ready with a non-string version", { type: "fred:ready", protocolVersion: 1 }],
    ["a navigate without a path", { type: "fred:navigate" }],
    ["a navigate with a non-string path", { type: "fred:navigate", path: 7 }],
    ["a navigate with a non-boolean replace", { type: "fred:navigate", path: "a", replace: "yes" }],
    ["a request without an id", { type: "fred:request", path: "items" }],
    ["a request with an empty id", { type: "fred:request", requestId: "", path: "items" }],
    ["a request with an overlong id", { type: "fred:request", requestId: "x".repeat(129), path: "items" }],
    ["a request with a disallowed method", { type: "fred:request", requestId: "r", path: "i", method: "TRACE" }],
    ["a request with non-string headers", { type: "fred:request", requestId: "r", path: "i", headers: { a: 1 } }],
    ["a request with array headers", { type: "fred:request", requestId: "r", path: "i", headers: [] }],
    ["a request with a non-string body", { type: "fred:request", requestId: "r", path: "i", body: { a: 1 } }],
  ])("drops %s", (_name, payload) => {
    expect(parseApplicationFrameMessage(payload)).toBeNull();
  });

  it("drops a request carrying more headers than the host will forward", () => {
    const headers = Object.fromEntries(Array.from({ length: 33 }, (_value, index) => [`h${index}`, "v"]));
    expect(parseApplicationFrameMessage({ type: "fred:request", requestId: "r", path: "i", headers })).toBeNull();
  });
});
