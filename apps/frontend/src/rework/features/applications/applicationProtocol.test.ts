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
import {
  ACCEPTED_APP_PROTOCOL_VERSIONS,
  APPLICATION_REQUEST_METHODS,
  FRED_APP_PROTOCOL_VERSION,
  MAX_APPLICATION_REQUEST_HEADERS,
  MAX_APPLICATION_REQUEST_ID_LENGTH,
  isProtectedApplicationHeader,
  normalizeApplicationRelativePath,
  parseApplicationFrameMessage,
  parseApplicationHostMessage,
} from "./applicationProtocol.ts";

const context = {
  team: { id: "team-1", name: "Team One", isPersonal: false },
  route: { basePath: "/team/team-1/apps/example", subPath: "reports" },
  locale: "en",
};

describe("protocol 1 golden wire shapes", () => {
  it("keeps the version and method limits public", () => {
    expect(FRED_APP_PROTOCOL_VERSION).toBe("1");
    expect(ACCEPTED_APP_PROTOCOL_VERSIONS).toEqual(["1"]);
    expect(APPLICATION_REQUEST_METHODS).toEqual(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]);
    expect(MAX_APPLICATION_REQUEST_ID_LENGTH).toBe(128);
    expect(MAX_APPLICATION_REQUEST_HEADERS).toBe(32);
  });

  it.each([
    [
      { type: "fred:ready", protocolVersion: "1" },
      { type: "fred:ready", protocolVersion: "1" },
    ],
    [
      { type: "fred:navigate", path: "reports" },
      { type: "fred:navigate", path: "reports", replace: false },
    ],
    [{ type: "fred:open-chat" }, { type: "fred:open-chat", sessionId: null }],
    [
      { type: "fred:request", requestId: "r1", path: "items" },
      { type: "fred:request", requestId: "r1", path: "items", method: "GET", headers: {}, body: null },
    ],
  ])("preserves a frame message", (wire, normalized) => {
    expect(parseApplicationFrameMessage(wire)).toEqual(normalized);
  });

  it.each([
    [
      { type: "fred:context", protocolVersion: "1", applicationId: "example", context },
      { type: "fred:context", protocolVersion: "1", applicationId: "example", context },
    ],
    [
      { type: "fred:route", subPath: "reports" },
      { type: "fred:route", subPath: "reports" },
    ],
    [
      { type: "fred:response", requestId: "r1", status: 201, headers: { "content-type": "text/plain" }, body: "ok" },
      { type: "fred:response", requestId: "r1", status: 201, headers: { "content-type": "text/plain" }, body: "ok" },
    ],
    [
      { type: "fred:response-error", requestId: "r1" },
      { type: "fred:response-error", requestId: "r1" },
    ],
  ])("preserves a host message", (wire, normalized) => {
    expect(parseApplicationHostMessage(wire)).toEqual(normalized);
  });
});

describe("protocol validation", () => {
  it.each(APPLICATION_REQUEST_METHODS)("accepts request method %s", (method) => {
    expect(parseApplicationFrameMessage({ type: "fred:request", requestId: "r", path: "items", method })).toMatchObject(
      {
        method,
      },
    );
  });

  it("accepts values at the request limits and rejects values beyond them", () => {
    const headers = Object.fromEntries(
      Array.from({ length: MAX_APPLICATION_REQUEST_HEADERS }, (_, index) => [`h${index}`, "v"]),
    );
    expect(
      parseApplicationFrameMessage({
        type: "fred:request",
        requestId: "r".repeat(MAX_APPLICATION_REQUEST_ID_LENGTH),
        path: "items",
        headers,
      }),
    ).not.toBeNull();
    expect(
      parseApplicationFrameMessage({ type: "fred:request", requestId: "r".repeat(129), path: "items" }),
    ).toBeNull();
    expect(
      parseApplicationFrameMessage({
        type: "fred:request",
        requestId: "r",
        path: "items",
        headers: { ...headers, extra: "v" },
      }),
    ).toBeNull();
  });

  it.each([
    null,
    [],
    { type: "fred:context", protocolVersion: "1", applicationId: "", context },
    { type: "fred:context", protocolVersion: "2", applicationId: "example", context: { ...context, locale: 2 } },
    { type: "fred:route", subPath: 1 },
    { type: "fred:response", requestId: "", status: 200, headers: {}, body: "" },
    { type: "fred:response", requestId: "r", status: 200, body: "ok" },
    { type: "fred:response", requestId: "r", status: 204, headers: [], body: "" },
    { type: "fred:response", requestId: "r", status: 199, headers: {}, body: "" },
    { type: "fred:response-error", requestId: {} },
  ])("rejects malformed host input", (wire) => {
    expect(parseApplicationHostMessage(wire)).toBeNull();
  });

  it.each([
    "Authorization",
    "authorization",
    "Cookie",
    "Host",
    "Proxy-Authorization",
    "X-Fred-Application-Id",
    "X-Fred-Team-Id",
  ])("identifies protected header %s", (header) => {
    expect(isProtectedApplicationHeader(header)).toBe(true);
  });

  it("does not classify ordinary headers as protected", () => {
    expect(isProtectedApplicationHeader("content-type")).toBe(false);
  });

  it.each([
    "/absolute",
    "https://elsewhere.test",
    "../outside",
    "%252e%252e/outside",
    "safe\\outside",
    "bad/%zz",
    "a#b",
  ])("rejects unsafe path %s", (value) => expect(() => normalizeApplicationRelativePath(value)).toThrow(TypeError));
});
