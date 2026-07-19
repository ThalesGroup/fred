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

import { describe, it, expect } from "vitest";
import { isProtectedAllowed } from "./Protected";

describe("isProtectedAllowed", () => {
  describe('requires="admin"', () => {
    it("allows a platform_admin", () => {
      expect(isProtectedAllowed("admin", { canAdmin: true, canObservePlatform: false })).toBe(true);
    });
    it("denies a platform_observer who is not also admin", () => {
      expect(isProtectedAllowed("admin", { canAdmin: false, canObservePlatform: true })).toBe(false);
    });
    it("denies a user with neither flag", () => {
      expect(isProtectedAllowed("admin", { canAdmin: false, canObservePlatform: false })).toBe(false);
    });
  });

  describe('requires="observer"', () => {
    it("allows a platform_observer", () => {
      expect(isProtectedAllowed("observer", { canAdmin: false, canObservePlatform: true })).toBe(true);
    });
    it("allows a platform_admin too, even without the observer flag set", () => {
      expect(isProtectedAllowed("observer", { canAdmin: true, canObservePlatform: false })).toBe(true);
    });
    it("denies a user with neither flag", () => {
      expect(isProtectedAllowed("observer", { canAdmin: false, canObservePlatform: false })).toBe(false);
    });
  });
});
