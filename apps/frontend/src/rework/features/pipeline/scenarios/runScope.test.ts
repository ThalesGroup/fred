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
import { expectRefused } from "./runScope";

const rejected = (status: number) => async () => {
  throw { status };
};

describe("expectRefused", () => {
  it.each([403, 404])("accepts explicit HTTP %i refusal", async (status) => {
    await expect(expectRefused(rejected(status), "reading fixture")).resolves.toBe(status);
  });

  it.each([401, 429, 500, 502])("rejects HTTP %i as evidence of isolation or deletion", async (status) => {
    await expect(expectRefused(rejected(status), "reading fixture")).rejects.toThrow(`HTTP ${status}`);
  });

  it("requires 404 when checking deletion in a space the caller still owns", async () => {
    await expect(expectRefused(rejected(403), "reading deleted prompt", [404])).rejects.toThrow("expected 404");
    await expect(expectRefused(rejected(404), "reading deleted prompt", [404])).resolves.toBe(404);
  });

  it("rejects a successful read and propagates transport errors", async () => {
    await expect(expectRefused(async () => ({}), "reading fixture")).rejects.toThrow("succeeded");
    await expect(
      expectRefused(async () => {
        throw new Error("network down");
      }, "reading fixture"),
    ).rejects.toThrow("network down");
  });
});
