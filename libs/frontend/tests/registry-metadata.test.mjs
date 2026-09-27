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
import http from "node:http";
import test from "node:test";

import {
  exactVersionMetadataUrl,
  fetchExactPackageMetadata,
  fetchPackageMetadata,
  packageMetadataUrl,
  waitForExactPackageMetadata,
  waitForPackageMetadata,
} from "../scripts/registry-metadata.mjs";

const candidate = {
  coordinate: "@fred-oss/design-tokens@0.1.0-alpha.1",
  integrity: `sha512-${Buffer.alloc(64, 1).toString("base64")}`,
};

function matchingMetadata(overrides = {}) {
  return {
    name: "@fred-oss/design-tokens",
    version: "0.1.0-alpha.1",
    dist: { integrity: candidate.integrity },
    ...overrides,
  };
}

async function controlledRegistry(context, responder) {
  const requests = [];
  const server = http.createServer((request, response) => {
    requests.push(request.url);
    responder(request, response, requests.length);
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  context.after(() => new Promise((resolve) => server.close(resolve)));
  return {
    registry: `http://127.0.0.1:${server.address().port}/`,
    requests,
  };
}

function json(response, status, value, headers = {}) {
  response.writeHead(status, {
    "content-type": "application/json",
    ...headers,
  });
  response.end(JSON.stringify(value));
}

test("exact metadata succeeds without consulting unavailable package-wide metadata", async (context) => {
  const controlled = await controlledRegistry(context, (request, response) => {
    if (request.url.endsWith("/0.1.0-alpha.1"))
      json(response, 200, matchingMetadata());
    else json(response, 404, { error: "package-wide metadata unavailable" });
  });
  const metadata = await fetchExactPackageMetadata({
    ...controlled,
    coordinate: candidate.coordinate,
    candidate,
  });
  assert.equal(metadata.name, "@fred-oss/design-tokens");
  assert.deepEqual(controlled.requests, [
    exactVersionMetadataUrl({
      coordinate: candidate.coordinate,
      registry: controlled.registry,
    }).pathname,
  ]);
});

test("only exact HTTP 404 is retried and six attempts are preserved", async (context) => {
  const delayed = await controlledRegistry(
    context,
    (_request, response, count) => {
      if (count < 3) json(response, 404, { error: "not visible" });
      else json(response, 200, matchingMetadata());
    },
  );
  await waitForExactPackageMetadata({
    candidate,
    registry: delayed.registry,
    inspectRegistry: fetchExactPackageMetadata,
    waitForVisibility: async () => {},
  });
  assert.equal(delayed.requests.length, 3);

  const absent = await controlledRegistry(context, (_request, response) => {
    json(response, 404, { error: "not visible" });
  });
  await assert.rejects(
    waitForExactPackageMetadata({
      candidate,
      registry: absent.registry,
      inspectRegistry: fetchExactPackageMetadata,
      waitForVisibility: async () => {},
    }),
    /exact-version metadata visibility retries exhausted after 6 reads/,
  );
  assert.equal(absent.requests.length, 6);
});

test("HTTP, redirect, JSON, identity, and integrity failures are immediate", async (context) => {
  const variants = [
    ["authentication", 401, matchingMetadata(), {}, /HTTP 401/],
    ["authorization", 403, matchingMetadata(), {}, /HTTP 403/],
    ["server", 500, matchingMetadata(), {}, /HTTP 500/],
    [
      "redirect",
      302,
      {},
      { location: "https://example.com/elsewhere" },
      /redirect is disallowed/,
    ],
    [
      "name",
      200,
      matchingMetadata({ name: "@fred-oss/other" }),
      {},
      /metadata name differs/,
    ],
    [
      "version",
      200,
      matchingMetadata({ version: "9.9.9" }),
      {},
      /metadata version differs/,
    ],
    [
      "integrity",
      200,
      matchingMetadata({ dist: { integrity: "sha512-wrong" } }),
      {},
      /registry integrity differs/,
    ],
  ];
  for (const [label, status, body, headers, expected] of variants) {
    await context.test(label, async (subcontext) => {
      const controlled = await controlledRegistry(
        subcontext,
        (_request, response) => json(response, status, body, headers),
      );
      await assert.rejects(
        waitForExactPackageMetadata({
          candidate,
          registry: controlled.registry,
          inspectRegistry: fetchExactPackageMetadata,
          waitForVisibility: async () => assert.fail("must not retry"),
        }),
        expected,
      );
      assert.equal(controlled.requests.length, 1);
    });
  }

  await context.test("malformed JSON", async (subcontext) => {
    const controlled = await controlledRegistry(
      subcontext,
      (_request, response) => {
        response.writeHead(200, { "content-type": "application/json" });
        response.end("{");
      },
    );
    await assert.rejects(
      fetchExactPackageMetadata({
        ...controlled,
        coordinate: candidate.coordinate,
        candidate,
      }),
      /metadata is malformed JSON/,
    );
    assert.equal(controlled.requests.length, 1);
  });
});

test("exact metadata requests are individually bounded", async (context) => {
  const controlled = await controlledRegistry(context, () => {});
  await assert.rejects(
    fetchExactPackageMetadata({
      ...controlled,
      coordinate: candidate.coordinate,
      candidate,
      requestTimeoutMilliseconds: 20,
    }),
    /exact-version metadata request failed/,
  );
  assert.equal(controlled.requests.length, 1);
});

test("package-wide readiness tolerates bounded visibility lag after exact metadata", async (context) => {
  const controlled = await controlledRegistry(
    context,
    (_request, response, count) => {
      if (count < 3) json(response, 404, { error: "not visible" });
      else
        json(response, 200, {
          name: "@fred-oss/design-tokens",
          versions: { "0.1.0-alpha.1": matchingMetadata() },
        });
    },
  );
  const metadata = await waitForPackageMetadata({
    ...controlled,
    coordinate: candidate.coordinate,
    candidate,
    visibilityDelayMilliseconds: 0,
  });
  assert.equal(metadata.name, "@fred-oss/design-tokens");
  assert.deepEqual(
    controlled.requests,
    Array(3).fill(
      packageMetadataUrl({
        coordinate: candidate.coordinate,
        registry: controlled.registry,
      }).pathname,
    ),
  );
});

test("package-wide readiness exhausts 404s and rejects malformed identity immediately", async (context) => {
  const absent = await controlledRegistry(context, (_request, response) => {
    json(response, 404, { error: "not visible" });
  });
  await assert.rejects(
    waitForPackageMetadata({
      ...absent,
      coordinate: candidate.coordinate,
      candidate,
      visibilityAttempts: 2,
      visibilityDelayMilliseconds: 0,
    }),
    /visibility retries exhausted after 2 reads/,
  );
  assert.equal(absent.requests.length, 2);

  const mismatched = await controlledRegistry(context, (_request, response) => {
    json(response, 200, {
      name: "@fred-oss/other",
      versions: { "0.1.0-alpha.1": matchingMetadata() },
    });
  });
  await assert.rejects(
    waitForPackageMetadata({
      ...mismatched,
      coordinate: candidate.coordinate,
      candidate,
      visibilityAttempts: 6,
      visibilityDelayMilliseconds: 0,
    }),
    /package metadata name differs/,
  );
  assert.equal(mismatched.requests.length, 1);

  await assert.rejects(
    fetchPackageMetadata({
      ...mismatched,
      coordinate: candidate.coordinate,
      candidate: { ...candidate, coordinate: "@fred-oss/other@0.1.0-alpha.1" },
    }),
    /candidate coordinate differs/,
  );
});
