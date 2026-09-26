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

import {
  createFredApplicationClient,
  type FredApplicationClient,
  type FredApplicationContext,
} from "@fred-oss/iframe-sdk";

interface ChildHarness {
  client: FredApplicationClient;
  connected: Promise<FredApplicationContext>;
  connectionError: string | null;
  routes: string[];
  contexts: FredApplicationContext[];
  stopContext(): void;
  navigate(path: string): void;
  openChat(sessionId?: string): void;
  request(
    path: string,
    method?: "GET" | "HEAD",
    timeoutMs?: number,
  ): Promise<{
    code?: string;
    headers?: Record<string, string>;
    status?: number;
    text?: string;
  }>;
  requestPair(): Promise<string[]>;
  capacity(): Promise<string>;
  abort(): Promise<string>;
  invalidInputs(): Promise<string[]>;
  dispose(): void;
}

declare global {
  interface Window {
    __fredChild: ChildHarness;
  }
}

const hostOrigin = new URLSearchParams(window.location.search).get(
  "hostOrigin",
);
if (!hostOrigin) throw new Error("hostOrigin is required");
const connectionTimeout = Number(
  new URLSearchParams(window.location.search).get("connectionTimeoutMs"),
);
const client = createFredApplicationClient({
  hostOrigin,
  applicationId: "example",
  connectionTimeoutMs:
    Number.isFinite(connectionTimeout) && connectionTimeout > 0
      ? connectionTimeout
      : undefined,
});
const routes: string[] = [];
const contexts: FredApplicationContext[] = [];
let stopContext = () => {};
let connectionError: string | null = null;
const connected = client.connect();
void connected
  .then(() => {
    client.onRoute(({ subPath }) => routes.push(subPath));
    stopContext = client.onContext((context) => contexts.push(context));
    const status = document.querySelector("#status");
    if (status) status.textContent = "Connected";
  })
  .catch((error: unknown) => {
    connectionError = error instanceof Error ? error.message : String(error);
  });

async function request(
  path: string,
  method: "GET" | "HEAD" = "GET",
  timeoutMs?: number,
) {
  try {
    const response = await client.request(path, { method, timeoutMs });
    return {
      status: response.status,
      headers: Object.fromEntries(response.headers),
      text: await response.text(),
    };
  } catch (error) {
    return { code: (error as { code?: string }).code ?? (error as Error).name };
  }
}

window.__fredChild = {
  client,
  connected,
  get connectionError() {
    return connectionError;
  },
  routes,
  contexts,
  stopContext: () => stopContext(),
  navigate: (path) => client.navigate(path),
  openChat: (sessionId) => client.openChat(sessionId),
  request,
  requestPair: async () => {
    const [one, two] = await Promise.all([
      request("pair/one"),
      request("pair/two"),
    ]);
    return [one.text ?? "", two.text ?? ""];
  },
  capacity: async () => {
    const pending = Array.from({ length: 16 }, (_, index) =>
      client.request(`pending/${index}`),
    );
    const result = await request("pending/overflow");
    client.dispose();
    await Promise.allSettled(pending);
    return result.code ?? "missing-error";
  },
  abort: async () => {
    const controller = new AbortController();
    const pending = client.request("pending/abort", {
      signal: controller.signal,
    });
    controller.abort();
    try {
      await pending;
      return "missing-error";
    } catch (error) {
      return (error as Error).name;
    }
  },
  invalidInputs: async () => {
    const codes: string[] = [];
    try {
      client.navigate("../outside");
    } catch (error) {
      codes.push((error as Error).name);
    }
    try {
      await client.request("items", {
        headers: { Authorization: "Bearer forbidden" },
      });
    } catch (error) {
      codes.push((error as { code?: string }).code ?? (error as Error).name);
    }
    return codes;
  },
  dispose: () => client.dispose(),
};
