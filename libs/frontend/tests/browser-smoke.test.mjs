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

import assert from "node:assert/strict";
import test from "node:test";

import { assertSuccessfulBrowserRequests } from "../scripts/browser-smoke.mjs";

test("rejects a failed stylesheet request", () => {
  assert.throws(
    () =>
      assertSuccessfulBrowserRequests({
        requestFailures: [
          {
            errorText: "net::ERR_FAILED",
            type: "stylesheet",
            url: "http://127.0.0.1/missing.css",
          },
        ],
        responses: [],
      }),
    /browser request failed/,
  );
});

test("rejects an unsuccessful stylesheet response", () => {
  assert.throws(
    () =>
      assertSuccessfulBrowserRequests({
        requestFailures: [],
        responses: [
          {
            status: 404,
            type: "stylesheet",
            url: "http://127.0.0.1/missing.css",
          },
        ],
      }),
    /unsuccessful HTTP 404.*missing\.css/,
  );
});
