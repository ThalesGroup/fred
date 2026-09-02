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

import type { ApplicationSummary } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";

/**
 * The wire contract between Fred and an application it hosts in an iframe.
 * Fred no longer compiles application code, so compatibility is settled at
 * runtime by the handshake below rather than by a build-time digest.
 */

/**
 * Protocol this host speaks. The accepted set is deliberately a set, not a
 * single literal: fork teams ship their own UI images on their own cadence, so
 * the host has to be able to admit more than one version at a time.
 */
export const FRED_APP_PROTOCOL_VERSION = "1";
export const ACCEPTED_APP_PROTOCOL_VERSIONS: readonly string[] = [FRED_APP_PROTOCOL_VERSION];

const ALLOWED_REQUEST_METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]);
const MAX_REQUEST_HEADERS = 32;
const MAX_REQUEST_ID_LENGTH = 128;

export interface FredApplicationFrameTarget {
  src: string;
  targetOrigin: string;
}

/**
 * Resolve the catalog's configured UI prefix into an iframe target. The value
 * is deployment configuration rather than Fred source, so it is validated
 * before it can become a src: a `javascript:` or `data:` entry would otherwise
 * run in whatever origin the frame inherits. The target origin is derived from
 * the same value, which is what keeps a later move to a separate origin a
 * configuration change rather than a code change.
 */
export function applicationFrameTarget(
  application: ApplicationSummary,
  baseOrigin: string,
): FredApplicationFrameTarget | null {
  if (!application.ui_prefix) return null;

  let url: URL;
  try {
    url = new URL(application.ui_prefix, baseOrigin);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  return { src: url.href, targetOrigin: url.origin };
}

/**
 * The only authenticated transport an application reaches. Fred owns the
 * service root, team scope, bearer lifecycle, and retry/logout behavior; the
 * application owns only its relative resource path and ordinary payload.
 * It stays on the host side of the channel — an application is never handed a
 * token, so moving the frame to another origin changes nothing here.
 */
export type FredApplicationRequest = (
  relativePath: string,
  init?: Pick<RequestInit, "method" | "headers" | "body" | "signal">,
) => Promise<Response>;

/** Everything the host hands a frame. Plain data only, so it survives cloning. */
export interface FredApplicationContext {
  team: {
    id: string;
    name: string;
    isPersonal: boolean;
  };
  route: {
    basePath: string;
    subPath: string;
  };
  locale: string;
}

export type ApplicationHostMessage =
  | { type: "fred:context"; protocolVersion: string; applicationId: string; context: FredApplicationContext }
  | { type: "fred:route"; subPath: string }
  | { type: "fred:response"; requestId: string; status: number; headers: Record<string, string>; body: string }
  | { type: "fred:response-error"; requestId: string };

export type ApplicationFrameMessage =
  | { type: "fred:ready"; protocolVersion: string }
  | { type: "fred:navigate"; path: string; replace: boolean }
  // The one message that leaves the application's subtree. It names no route:
  // the frame states an intent and the host decides where that lands, so the
  // surface an application can reach is fixed at review time. `sessionId` is a
  // CANDIDATE, never a destination — the host honours it only after matching
  // it against the caller's own sessions, so the worst an application can do
  // is reopen a conversation its user already owns.
  | { type: "fred:open-chat"; sessionId: string | null }
  | {
      type: "fred:request";
      requestId: string;
      path: string;
      method: string;
      headers: Record<string, string>;
      body: string | null;
    };

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function parseHeaders(value: unknown): Record<string, string> | null {
  if (value === undefined) return {};
  const record = asRecord(value);
  if (!record) return null;

  const entries = Object.entries(record);
  if (entries.length > MAX_REQUEST_HEADERS) return null;
  if (entries.some(([, headerValue]) => typeof headerValue !== "string")) return null;
  return Object.fromEntries(entries as [string, string][]);
}

/**
 * Admit only the closed set of frame messages. Everything else — extension
 * chatter, a future protocol, a hostile payload — returns null so it can be
 * dropped before it reaches Fred state, the router, or diagnostics.
 */
export function parseApplicationFrameMessage(data: unknown): ApplicationFrameMessage | null {
  const message = asRecord(data);
  if (!message) return null;

  switch (message.type) {
    case "fred:ready":
      if (typeof message.protocolVersion !== "string") return null;
      return { type: "fred:ready", protocolVersion: message.protocolVersion };

    case "fred:open-chat":
      return {
        type: "fred:open-chat",
        sessionId: typeof message.sessionId === "string" && message.sessionId ? message.sessionId : null,
      };

    case "fred:navigate":
      if (typeof message.path !== "string") return null;
      if (message.replace !== undefined && typeof message.replace !== "boolean") return null;
      return { type: "fred:navigate", path: message.path, replace: message.replace === true };

    case "fred:request": {
      const { requestId, path } = message;
      if (typeof requestId !== "string" || requestId.length === 0 || requestId.length > MAX_REQUEST_ID_LENGTH) {
        return null;
      }
      if (typeof path !== "string") return null;

      const method = message.method === undefined ? "GET" : message.method;
      if (typeof method !== "string" || !ALLOWED_REQUEST_METHODS.has(method)) return null;

      const headers = parseHeaders(message.headers);
      if (!headers) return null;
      if (message.body !== undefined && message.body !== null && typeof message.body !== "string") return null;

      return {
        type: "fred:request",
        requestId,
        path,
        method,
        headers,
        body: typeof message.body === "string" ? message.body : null,
      };
    }

    default:
      return null;
  }
}
