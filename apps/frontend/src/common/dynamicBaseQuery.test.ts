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

import { describe, expect, it, vi } from "vitest";

vi.mock("../security/KeycloakService", () => ({ KeyCloakService: {} }));

import { serializeQueryParams } from "./dynamicBaseQuery";

describe("serializeQueryParams", () => {
  it("repeats the key of an array, as FastAPI reads a list query parameter", () => {
    expect(serializeQueryParams({ scope: "user", task_id: ["a", "b"] })).toBe("scope=user&task_id=a&task_id=b");
  });

  it("serializes scalars as before and drops undefined values", () => {
    expect(serializeQueryParams({ limit: 10, flag: true, team_id: undefined })).toBe("limit=10&flag=true");
  });
});
