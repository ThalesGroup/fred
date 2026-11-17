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
import { test } from "node:test";
import { createServer as createHttpServer } from "node:http";
import { createServer } from "vite";
import { loadApplicationProxyConfig } from "./application-proxy.mjs";

test("fixed prefixes share Control Plane with no path rewriting", () => {
  const proxy = loadApplicationProxyConfig("http://localhost:8222");
  for (const prefix of ["apps", "app-services"]) {
    const [key, options] = Object.entries(proxy).find(([key]) => new RegExp(key).test(`/${prefix}/any-id/a?b=c`));
    assert.equal(new RegExp(key).test(`/${prefix}-extra/x`), false);
    assert.equal(options.target, "http://localhost:8222");
    assert.equal(options.rewrite, undefined);
    assert.ok(options.proxyTimeout >= 180000);
  }
  process.env.FRONTEND_APPLICATIONS_JSON = "[]";
  try {
    assert.throws(() => loadApplicationProxyConfig("http://localhost:8222"), /Admin > Applications/);
  } finally {
    delete process.env.FRONTEND_APPLICATIONS_JSON;
  }
});

test("Vite preserves paths, bearer, multipart, binary and incremental SSE", async () => {
  const seen = [];
  const upstream = createHttpServer(async (req, res) => {
    const parts = [];
    for await (const chunk of req) parts.push(chunk);
    const body = Buffer.concat(parts);
    seen.push({ url: req.url, headers: req.headers, body });
    if (req.url.endsWith("/events")) {
      res.writeHead(200, { "content-type": "text/event-stream" });
      res.write("data: first\n\n");
      setTimeout(() => res.end("data: last\n\n"), 500);
    } else {
      res.writeHead(req.url.includes("missing") ? 404 : 200, { "content-type": "application/octet-stream" });
      res.end(body.length ? body : Buffer.from([0, 255, 10, 13]));
    }
  });
  await new Promise((resolve) => upstream.listen(0, "127.0.0.1", resolve));
  const server = await createServer({
    configFile: false,
    logLevel: "silent",
    server: {
      host: "127.0.0.1",
      port: 0,
      proxy: loadApplicationProxyConfig(`http://127.0.0.1:${upstream.address().port}`),
    },
  });
  try {
    await server.listen();
    const base = `http://127.0.0.1:${server.httpServer.address().port}`;
    const path = "/app-services/evaluation/spaces/a/upload?probe=a%20b";
    const body = Buffer.from(
      '--boundary\r\nContent-Disposition: form-data; name="file"\r\n\r\nvalue\r\n--boundary--\r\n',
    );
    const response = await fetch(base + path, {
      method: "POST",
      headers: {
        authorization: "Bearer test",
        "content-type": "multipart/form-data; boundary=boundary",
      },
      body,
    });
    assert.deepEqual(Buffer.from(await response.arrayBuffer()), body);
    assert.equal(seen[0].url, path);
    assert.equal(seen[0].headers.authorization, "Bearer test");
    assert.equal(seen[0].headers["content-type"], "multipart/form-data; boundary=boundary");
    const binary = await fetch(base + "/apps/evaluation/assets/main.mjs?v=2");
    assert.deepEqual(Buffer.from(await binary.arrayBuffer()), Buffer.from([0, 255, 10, 13]));
    assert.equal(seen[1].url, "/apps/evaluation/assets/main.mjs?v=2");
    assert.equal((await fetch(base + "/apps/missing/")).status, 404);
    const events = await fetch(base + "/app-services/evaluation/events");
    const reader = events.body.getReader();
    const first = await reader.read();
    assert.equal(new TextDecoder().decode(first.value), "data: first\n\n");
    await reader.cancel();
  } finally {
    await server.close();
    upstream.closeAllConnections();
    await new Promise((resolve) => upstream.close(resolve));
  }
});
