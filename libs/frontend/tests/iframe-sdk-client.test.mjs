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
import { pathToFileURL } from "node:url";
import path from "node:path";

import { buildIframeSdk, packageRoot } from "../scripts/build-iframe-sdk.mjs";

await buildIframeSdk();
const { FredApplicationClientError, createFredApplicationClient } =
  await import(
    `${pathToFileURL(path.join(packageRoot, "dist/index.js")).href}?client-test=${Date.now()}`
  );

const hostOrigin = "https://fred.example";
const applicationContext = {
  team: { id: "team-1", name: "Team One", isPersonal: false },
  route: { basePath: "/team/team-1/apps/example", subPath: "A" },
  locale: "en",
};

class FakeWindow {
  listeners = new Set();
  posts = [];
  throwOnPost = false;
  crypto = globalThis.crypto;
  parent = {
    postMessage: (message, origin) => {
      if (this.throwOnPost) throw new DOMException("blocked", "SecurityError");
      assert(
        this.listeners.size > 0,
        "listener must be installed before ready is posted",
      );
      this.posts.push({ message, origin });
    },
  };

  addEventListener(type, listener) {
    if (type === "message") this.listeners.add(listener);
  }

  removeEventListener(type, listener) {
    if (type === "message") this.listeners.delete(listener);
  }

  emit(data, { origin = hostOrigin, source = this.parent } = {}) {
    for (const listener of [...this.listeners])
      listener({ data, origin, source });
  }
}

function installWindow(fake) {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: fake,
    writable: true,
  });
  return () => {
    if (descriptor) Object.defineProperty(globalThis, "window", descriptor);
    else delete globalThis.window;
  };
}

function contextMessage(overrides = {}) {
  return {
    type: "fred:context",
    protocolVersion: "1",
    applicationId: "example",
    context: applicationContext,
    ...overrides,
  };
}

async function connectedClient(options = {}, configure = () => {}) {
  const fake = new FakeWindow();
  configure(fake);
  const restore = installWindow(fake);
  const client = createFredApplicationClient({
    hostOrigin,
    applicationId: "example",
    ...options,
  });
  const connection = client.connect();
  fake.emit(contextMessage());
  await connection;
  return { client, fake, restore };
}

test("validates configuration and requires an iframe parent", () => {
  const top = new FakeWindow();
  top.parent = top;
  const restore = installWindow(top);
  try {
    assert.throws(
      () =>
        createFredApplicationClient({ hostOrigin, applicationId: "example" }),
      (error) =>
        error instanceof FredApplicationClientError &&
        error.code === "missing-parent",
    );
    for (const invalidOrigin of [
      "*",
      "javascript:alert(1)",
      "https://fred.example/path",
      "https://u:p@fred.example",
    ]) {
      assert.throws(
        () =>
          createFredApplicationClient({
            hostOrigin: invalidOrigin,
            applicationId: "example",
          }),
        (error) => error.code === "invalid-configuration",
      );
    }
  } finally {
    restore();
  }
});

test("shares connection state, retries ready, and admits only the configured parent", async () => {
  const fake = new FakeWindow();
  const restore = installWindow(fake);
  try {
    const client = createFredApplicationClient({
      hostOrigin,
      applicationId: "example",
      connectionTimeoutMs: 1_000,
    });
    const first = client.connect();
    assert.equal(client.connect(), first);
    assert.deepEqual(fake.posts[0], {
      message: { type: "fred:ready", protocolVersion: "1" },
      origin: hostOrigin,
    });
    fake.emit(contextMessage(), { origin: "https://attacker.example" });
    fake.emit(contextMessage(), { source: {} });
    await new Promise((resolve) => setTimeout(resolve, 520));
    assert(fake.posts.length >= 2, "ready was not retried");
    fake.emit(contextMessage());
    const context = await first;
    assert.equal(context, client.context);
    assert(Object.isFrozen(context));
    assert(Object.isFrozen(context.team));
    const readyCount = fake.posts.length;
    await new Promise((resolve) => setTimeout(resolve, 520));
    assert.equal(
      fake.posts.length,
      readyCount,
      "ready retry continued after context",
    );
    client.dispose();
  } finally {
    restore();
  }
});

test("fails malformed, unsupported, mismatched, and timed-out connections actionably", async () => {
  for (const [message, code] of [
    [
      {
        type: "fred:context",
        protocolVersion: "1",
        applicationId: "example",
        context: {},
      },
      "malformed-context",
    ],
    [contextMessage({ protocolVersion: "2" }), "unsupported-protocol"],
    [contextMessage({ applicationId: "other" }), "application-mismatch"],
  ]) {
    const fake = new FakeWindow();
    const restore = installWindow(fake);
    try {
      const client = createFredApplicationClient({
        hostOrigin,
        applicationId: "example",
        connectionTimeoutMs: 50,
      });
      const connection = client.connect();
      fake.emit(message);
      await assert.rejects(connection, (error) => error.code === code);
      assert.equal(fake.listeners.size, 0);
    } finally {
      restore();
    }
  }
  const fake = new FakeWindow();
  const restore = installWindow(fake);
  try {
    const client = createFredApplicationClient({
      hostOrigin,
      applicationId: "example",
      connectionTimeoutMs: 10,
    });
    await assert.rejects(
      client.connect(),
      (error) => error.code === "connection-timeout",
    );
  } finally {
    restore();
  }
});

test("delivers every accepted route event, including host A, child B, host A", async () => {
  const { client, fake, restore } = await connectedClient();
  try {
    const routes = [];
    const unsubscribe = client.onRoute((route) => routes.push(route.subPath));
    fake.emit({ type: "fred:route", subPath: "A" });
    client.navigate("B");
    fake.emit({ type: "fred:route", subPath: "A" });
    assert.deepEqual(routes, ["A", "A"]);
    assert.deepEqual(fake.posts.at(-1), {
      message: { type: "fred:navigate", path: "B", replace: false },
      origin: hostOrigin,
    });
    unsubscribe();
    unsubscribe();
    fake.emit({ type: "fred:route", subPath: "A" });
    assert.deepEqual(routes, ["A", "A"]);
  } finally {
    client.dispose();
    restore();
  }
});

test("delivers later valid contexts, including repeats, without replay or route events", async () => {
  const fake = new FakeWindow();
  const restore = installWindow(fake);
  try {
    const client = createFredApplicationClient({
      hostOrigin,
      applicationId: "example",
    });
    assert.throws(
      () => client.onContext(() => {}),
      (error) => error.code === "not-connected",
    );
    const initial = client.connect();
    fake.emit(contextMessage());
    assert.equal((await initial).theme, undefined);
    const contexts = [];
    const routes = [];
    const unsubscribe = client.onContext((context) => contexts.push(context));
    client.onRoute((route) => routes.push(route));
    assert.equal(contexts.length, 0);
    const dark = { ...applicationContext, theme: "dark" };
    fake.emit(contextMessage({ context: dark }));
    fake.emit(contextMessage({ context: dark }));
    fake.emit(
      contextMessage({ context: { ...dark, theme: "light", locale: "fr" } }),
    );
    assert.deepEqual(
      contexts.map(({ theme, locale }) => [theme, locale]),
      [
        ["dark", "en"],
        ["dark", "en"],
        ["light", "fr"],
      ],
    );
    assert(Object.isFrozen(client.context));
    assert.equal(client.context.theme, "light");
    assert.deepEqual(routes, []);
    unsubscribe();
    unsubscribe();
    fake.emit(contextMessage({ context: dark }));
    assert.equal(contexts.length, 3);
    client.dispose();
    fake.emit(contextMessage({ context: dark }));
    assert.equal(contexts.length, 3);
  } finally {
    restore();
  }
});

test("later malformed or misattributed context leaves state and requests intact", async () => {
  const { client, fake, restore } = await connectedClient();
  try {
    const contexts = [];
    client.onContext((context) => contexts.push(context));
    const pending = client.request("items");
    const request = fake.posts.at(-1).message;
    const initial = client.context;
    for (const message of [
      contextMessage({ context: { ...applicationContext, theme: "system" } }),
      contextMessage({ context: { ...applicationContext, theme: null } }),
      contextMessage({ context: {} }),
      contextMessage({ applicationId: "other" }),
      contextMessage({ protocolVersion: "2" }),
    ])
      fake.emit(message);
    fake.emit(
      contextMessage({ context: { ...applicationContext, theme: "dark" } }),
      { origin: "https://attacker.example" },
    );
    fake.emit(
      contextMessage({ context: { ...applicationContext, theme: "dark" } }),
      { source: {} },
    );
    assert.equal(client.context, initial);
    assert.equal(contexts.length, 0);
    fake.emit({
      type: "fred:response",
      requestId: request.requestId,
      status: 200,
      headers: {},
      body: "ok",
    });
    assert.equal(await (await pending).text(), "ok");
  } finally {
    client.dispose();
    restore();
  }
});

test("context subscribers use snapshot delivery and isolate listener exceptions", async () => {
  const { client, fake, restore } = await connectedClient();
  const originalReportError = globalThis.reportError;
  const errors = [];
  globalThis.reportError = (error) => errors.push(error);
  try {
    const received = [];
    let unsubscribe;
    client.onContext(() => {
      unsubscribe();
      throw new Error("listener failed");
    });
    unsubscribe = client.onContext((context) => received.push(context.theme));
    fake.emit(
      contextMessage({ context: { ...applicationContext, theme: "dark" } }),
    );
    assert.deepEqual(received, ["dark"]);
    assert.equal(errors.length, 1);
    fake.emit(
      contextMessage({ context: { ...applicationContext, theme: "light" } }),
    );
    assert.deepEqual(received, ["dark"]);
  } finally {
    client.dispose();
    globalThis.reportError = originalReportError;
    restore();
  }
});

test("posts normalized navigation and open-chat intents and rejects escaping paths", async () => {
  const { client, fake, restore } = await connectedClient();
  try {
    client.navigate("reports/2", { replace: true });
    client.openChat("session-1");
    client.openChat("");
    assert.deepEqual(
      fake.posts.slice(-3).map(({ message }) => message),
      [
        { type: "fred:navigate", path: "reports/2", replace: true },
        { type: "fred:open-chat", sessionId: "session-1" },
        { type: "fred:open-chat", sessionId: null },
      ],
    );
    assert.throws(() => client.navigate("../outside"), TypeError);
    assert.throws(() => client.request("/outside"), TypeError);
  } finally {
    client.dispose();
    restore();
  }
});

test("correlates out-of-order replies and ignores duplicate or unknown request IDs", async () => {
  const { client, fake, restore } = await connectedClient();
  try {
    const first = client.request("first");
    const second = client.request("second");
    const requests = fake.posts
      .filter(({ message }) => message.type === "fred:request")
      .map(({ message }) => message);
    fake.emit({
      type: "fred:response",
      requestId: requests[1].requestId,
      status: 200,
      headers: {},
      body: "second",
    });
    fake.emit({
      type: "fred:response",
      requestId: "unknown",
      status: 200,
      headers: {},
      body: "unknown",
    });
    fake.emit({
      type: "fred:response",
      requestId: requests[1].requestId,
      status: 200,
      headers: {},
      body: "duplicate",
    });
    fake.emit({
      type: "fred:response",
      requestId: requests[0].requestId,
      status: 200,
      headers: {},
      body: "first",
    });
    assert.equal(await (await first).text(), "first");
    assert.equal(await (await second).text(), "second");
  } finally {
    client.dispose();
    restore();
  }
});

test("ignores a response missing required headers until a valid response arrives", async () => {
  const { client, fake, restore } = await connectedClient();
  try {
    const pending = client.request("reports");
    const request = fake.posts.find(
      ({ message }) => message.type === "fred:request",
    ).message;
    fake.emit({
      type: "fred:response",
      requestId: request.requestId,
      status: 200,
      body: "malformed",
    });
    fake.emit({
      type: "fred:response",
      requestId: request.requestId,
      status: 200,
      headers: {},
      body: "valid",
    });
    assert.equal(await (await pending).text(), "valid");
  } finally {
    client.dispose();
    restore();
  }
});

test("generates request IDs when crypto.randomUUID is unavailable", async () => {
  const { client, fake, restore } = await connectedClient({}, (childWindow) => {
    childWindow.crypto = {
      getRandomValues(bytes) {
        bytes.forEach((_, index) => {
          bytes[index] = index;
        });
        return bytes;
      },
    };
  });
  try {
    const pending = client.request("fallback-id");
    const request = fake.posts.at(-1).message;
    assert.match(
      request.requestId,
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    fake.emit({
      type: "fred:response",
      requestId: request.requestId,
      status: 200,
      headers: {},
      body: "ok",
    });
    assert.equal(await (await pending).text(), "ok");
  } finally {
    client.dispose();
    restore();
  }
});

test("resolves HTTP errors and reconstructs all bodyless responses", async () => {
  const { client, fake, restore } = await connectedClient();
  try {
    for (const [method, status, body] of [
      ["GET", 403, "forbidden"],
      ["HEAD", 200, ""],
      ["GET", 204, ""],
      ["GET", 205, ""],
      ["GET", 304, ""],
      ["GET", 503, "down"],
    ]) {
      const responsePromise = client.request("items", { method });
      const request = fake.posts.at(-1).message;
      fake.emit({
        type: "fred:response",
        requestId: request.requestId,
        status,
        headers: { "x-result": "visible" },
        body,
      });
      const response = await responsePromise;
      assert.equal(response.status, status);
      assert.equal(response.headers.get("x-result"), "visible");
      assert.equal(response.headers.get("content-type"), null);
      assert.equal(await response.text(), body);
    }
    const transport = client.request("items");
    fake.emit({
      type: "fred:response-error",
      requestId: fake.posts.at(-1).message.requestId,
    });
    await assert.rejects(
      transport,
      (error) => error.code === "transport-error",
    );
  } finally {
    client.dispose();
    restore();
  }
});

test("rejects an invalid host response without stranding pending work", async () => {
  const { client, fake, restore } = await connectedClient({
    requestTimeoutMs: 1_000,
  });
  try {
    const invalidResponse = client.request("invalid-response");
    fake.emit({
      type: "fred:response",
      requestId: fake.posts.at(-1).message.requestId,
      status: 200,
      headers: { "invalid\nname": "value" },
      body: "ignored",
    });
    await assert.rejects(
      invalidResponse,
      (error) => error.code === "transport-error",
    );

    const nextResponse = client.request("valid-response");
    fake.emit({
      type: "fred:response",
      requestId: fake.posts.at(-1).message.requestId,
      status: 200,
      headers: {},
      body: "ok",
    });
    const response = await nextResponse;
    assert.equal(response.headers.get("content-type"), null);
    assert.equal(await response.text(), "ok");
  } finally {
    client.dispose();
    restore();
  }
});

test("reports local postMessage failures and releases pending work", async () => {
  const connectingWindow = new FakeWindow();
  connectingWindow.throwOnPost = true;
  const restoreConnecting = installWindow(connectingWindow);
  try {
    const client = createFredApplicationClient({
      hostOrigin,
      applicationId: "example",
    });
    await assert.rejects(
      client.connect(),
      (error) => error.code === "transport-error",
    );
    assert.equal(connectingWindow.listeners.size, 0);
  } finally {
    restoreConnecting();
  }

  const connected = await connectedClient();
  try {
    connected.fake.throwOnPost = true;
    await assert.rejects(
      connected.client.request("items"),
      (error) => error.code === "transport-error",
    );
    connected.fake.throwOnPost = false;
    const nextRequest = connected.client.request("items");
    const requestId = connected.fake.posts.at(-1).message.requestId;
    connected.fake.emit({
      type: "fred:response",
      requestId,
      status: 200,
      headers: {},
      body: "ok",
    });
    assert.equal(await (await nextRequest).text(), "ok");
  } finally {
    connected.client.dispose();
    connected.restore();
  }
});

test("enforces request validation, capacity, local timeout, abort, and disposal", async () => {
  const { client, fake, restore } = await connectedClient({
    requestTimeoutMs: 1_000,
  });
  try {
    await assert.rejects(
      client.request("items", { headers: { Authorization: "Bearer leaked" } }),
      (error) => error.code === "invalid-request",
    );
    await assert.rejects(
      client.request("items", { method: "TRACE" }),
      (error) => error.code === "invalid-request",
    );
    const pending = Array.from({ length: 16 }, (_, index) =>
      client.request(`items/${index}`),
    );
    await assert.rejects(
      client.request("overflow"),
      (error) => error.code === "request-capacity",
    );
    client.dispose();
    await Promise.all(
      pending.map((request) =>
        assert.rejects(request, (error) => error.code === "disposed"),
      ),
    );
    assert.equal(fake.listeners.size, 0);
    assert.throws(
      () => client.navigate("items"),
      (error) => error.code === "disposed",
    );
  } finally {
    client.dispose();
    restore();
  }

  const timed = await connectedClient();
  try {
    const request = timed.client.request("slow", { timeoutMs: 10 });
    const requestId = timed.fake.posts.at(-1).message.requestId;
    await assert.rejects(request, (error) => error.code === "request-timeout");
    timed.fake.emit({
      type: "fred:response",
      requestId,
      status: 200,
      headers: {},
      body: "late",
    });
    const controller = new AbortController();
    const aborted = timed.client.request("abort", {
      signal: controller.signal,
    });
    controller.abort();
    await assert.rejects(aborted, (error) => error.name === "AbortError");
  } finally {
    timed.client.dispose();
    timed.restore();
  }
});
