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
