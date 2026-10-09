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

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let userId: string | null = "alice";
let claims: Record<string, unknown> | null = { sid: "login-1" };

vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetUserId: () => userId,
    GetTokenParsed: () => claims,
  },
}));

import { markClosedThisSession, wasClosedThisSession } from "./patchNoteSession";

const p1 = { id: "p1", content_version: 1 };
const p2 = { id: "p2", content_version: 1 };

beforeEach(() => {
  userId = "alice";
  claims = { sid: "login-1" };
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("patchNoteSession", () => {
  it("round-trips a closed id", () => {
    expect(wasClosedThisSession(p1)).toBe(false);

    markClosedThisSession(p1);

    expect(wasClosedThisSession(p1)).toBe(true);
    expect(wasClosedThisSession(p2)).toBe(false);
    expect(window.localStorage.getItem("fred.patchNote.closed.alice.login-1.p1.v1")).toBe("1");
  });

  it("shows a new edition of the same note again", () => {
    markClosedThisSession(p1);

    expect(wasClosedThisSession({ ...p1, content_version: 2 })).toBe(false);
  });

  it("is shared by a new tab of the same sign-in", () => {
    markClosedThisSession(p1);
    // A new tab starts with an empty sessionStorage but the same login session.
    window.sessionStorage.clear();

    expect(wasClosedThisSession(p1)).toBe(true);
  });

  it("shows the note again after a new sign-in", () => {
    markClosedThisSession(p1);

    claims = { session_state: "login-2" };

    expect(wasClosedThisSession(p1)).toBe(false);
  });

  it("does not leak to another user of the same browser", () => {
    markClosedThisSession(p1);

    userId = "bob";

    expect(wasClosedThisSession(p1)).toBe(false);
  });

  it("prunes the user's flags from earlier sign-ins only", () => {
    markClosedThisSession(p1);
    userId = "bob";
    markClosedThisSession(p1);
    userId = "alice";
    claims = { sid: "login-2" };

    markClosedThisSession(p2);

    expect(window.localStorage.getItem("fred.patchNote.closed.alice.login-1.p1.v1")).toBeNull();
    expect(window.localStorage.getItem("fred.patchNote.closed.alice.login-2.p2.v1")).toBe("1");
    expect(window.localStorage.getItem("fred.patchNote.closed.bob.login-1.p1.v1")).toBe("1");
  });

  it("falls back to sessionStorage, per user, without a login-session id", () => {
    claims = {};

    markClosedThisSession(p1);

    expect(window.sessionStorage.getItem("fred.patchNote.closed.alice.p1.v1")).toBe("1");
    expect(window.localStorage.length).toBe(0);
    expect(wasClosedThisSession(p1)).toBe(true);
    userId = "bob";
    expect(wasClosedThisSession(p1)).toBe(false);
  });

  it("degrades when storage throws", () => {
    // Blocked site data: reading the storage object itself throws a SecurityError.
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect(() => markClosedThisSession(p1)).not.toThrow();
    expect(wasClosedThisSession(p1)).toBe(false);
    claims = {};
    expect(() => markClosedThisSession(p1)).not.toThrow();
    expect(wasClosedThisSession(p1)).toBe(false);
  });
});
