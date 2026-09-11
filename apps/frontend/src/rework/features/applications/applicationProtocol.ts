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

/** The cloneable protocol shared by FRED's host and external child applications. */
export const FRED_APP_PROTOCOL_VERSION = "1";
export const ACCEPTED_APP_PROTOCOL_VERSIONS: readonly string[] = [FRED_APP_PROTOCOL_VERSION];

export const APPLICATION_REQUEST_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"] as const;
export type ApplicationRequestMethod = (typeof APPLICATION_REQUEST_METHODS)[number];
export const MAX_APPLICATION_REQUEST_HEADERS = 32;
export const MAX_APPLICATION_REQUEST_ID_LENGTH = 128;
export const MAX_PENDING_APPLICATION_REQUESTS = 16;

export const PROTECTED_APPLICATION_HEADERS = [
  "authorization",
  "cookie",
  "host",
  "proxy-authorization",
  "x-fred-application-id",
  "x-fred-team-id",
] as const;

const ALLOWED_REQUEST_METHODS = new Set<string>(APPLICATION_REQUEST_METHODS);
const PROTECTED_HEADERS = new Set<string>(PROTECTED_APPLICATION_HEADERS);
const SCHEME = /^[a-z][a-z\d+.-]*:/i;

export interface FredApplicationContext {
  readonly team: {
    readonly id: string;
    readonly name: string;
    readonly isPersonal: boolean;
  };
  readonly route: {
    readonly basePath: string;
    readonly subPath: string;
  };
  readonly locale: string;
}

export interface FredApplicationRoute {
  readonly subPath: string;
}

export type ApplicationHostMessage =
  | { type: "fred:context"; protocolVersion: string; applicationId: string; context: FredApplicationContext }
  | { type: "fred:route"; subPath: string }
  | { type: "fred:response"; requestId: string; status: number; headers: Record<string, string>; body: string }
  | { type: "fred:response-error"; requestId: string };

export type ApplicationFrameMessage =
  | { type: "fred:ready"; protocolVersion: string }
  | { type: "fred:navigate"; path: string; replace: boolean }
  | { type: "fred:open-chat"; sessionId: string | null }
  | {
      type: "fred:request";
      requestId: string;
      path: string;
      method: ApplicationRequestMethod;
      headers: Record<string, string>;
      body: string | null;
    };

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function parseStringHeaders(value: unknown, maximum?: number): Record<string, string> | null {
  if (value === undefined) return {};
  const record = asRecord(value);
  if (!record) return null;
  const entries = Object.entries(record);
  if (maximum !== undefined && entries.length > maximum) return null;
  if (entries.some(([, headerValue]) => typeof headerValue !== "string")) return null;
  return Object.fromEntries(entries as [string, string][]);
}

function validRequestId(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= MAX_APPLICATION_REQUEST_ID_LENGTH;
}

function parseContext(value: unknown): FredApplicationContext | null {
  const context = asRecord(value);
  const team = asRecord(context?.team);
  const route = asRecord(context?.route);
  if (
    !context ||
    !team ||
    !route ||
    typeof team.id !== "string" ||
    typeof team.name !== "string" ||
    typeof team.isPersonal !== "boolean" ||
    typeof route.basePath !== "string" ||
    typeof route.subPath !== "string" ||
    typeof context.locale !== "string"
  ) {
    return null;
  }
  return {
    team: { id: team.id, name: team.name, isPersonal: team.isPersonal },
    route: { basePath: route.basePath, subPath: route.subPath },
    locale: context.locale,
  };
}

/** Admit only the closed set of protocol-1 messages sent by a child frame. */
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
      if (!validRequestId(message.requestId) || typeof message.path !== "string") return null;
      const method = message.method === undefined ? "GET" : message.method;
      if (typeof method !== "string" || !ALLOWED_REQUEST_METHODS.has(method)) return null;
      const headers = parseStringHeaders(message.headers, MAX_APPLICATION_REQUEST_HEADERS);
      if (!headers) return null;
      if (message.body !== undefined && message.body !== null && typeof message.body !== "string") return null;
      return {
        type: "fred:request",
        requestId: message.requestId,
        path: message.path,
        method: method as ApplicationRequestMethod,
        headers,
        body: typeof message.body === "string" ? message.body : null,
      };
    }
    default:
      return null;
  }
}

/** Admit only the closed set of protocol-1 messages sent by the FRED host. */
export function parseApplicationHostMessage(data: unknown): ApplicationHostMessage | null {
  const message = asRecord(data);
  if (!message) return null;

  switch (message.type) {
    case "fred:context": {
      if (
        typeof message.protocolVersion !== "string" ||
        typeof message.applicationId !== "string" ||
        message.applicationId.length === 0
      ) {
        return null;
      }
      const context = parseContext(message.context);
      return context
        ? {
            type: "fred:context",
            protocolVersion: message.protocolVersion,
            applicationId: message.applicationId,
            context,
          }
        : null;
    }
    case "fred:route":
      return typeof message.subPath === "string" ? { type: "fred:route", subPath: message.subPath } : null;
    case "fred:response": {
      if (!validRequestId(message.requestId)) return null;
      if (!Number.isInteger(message.status) || (message.status as number) < 200 || (message.status as number) > 599) {
        return null;
      }
      if (message.headers === undefined) return null;
      const headers = parseStringHeaders(message.headers);
      if (!headers || typeof message.body !== "string") return null;
      return {
        type: "fred:response",
        requestId: message.requestId,
        status: message.status as number,
        headers,
        body: message.body,
      };
    }
    case "fred:response-error":
      return validRequestId(message.requestId) ? { type: "fred:response-error", requestId: message.requestId } : null;
    default:
      return null;
  }
}

export function isProtectedApplicationHeader(name: string): boolean {
  return PROTECTED_HEADERS.has(name.toLowerCase());
}

function fullyDecodeSegment(rawSegment: string): string {
  let decoded = rawSegment;
  for (let iteration = 0; iteration <= rawSegment.length; iteration += 1) {
    try {
      const decodable = iteration === 0 ? decoded : decoded.replace(/%(?![0-9A-Fa-f]{2})/g, "%25");
      const next = decodeURIComponent(decodable);
      if (next === decoded) return decoded;
      decoded = next;
    } catch {
      throw new TypeError("Application paths must use valid percent-encoding at every layer");
    }
  }
  throw new TypeError("Application path encoding is too deeply nested");
}

/** Validate an application path without changing the bytes sent to the host. */
export function normalizeApplicationRelativePath(relativePath: string): string {
  if (typeof relativePath !== "string") throw new TypeError("Application paths must be strings");
  if (relativePath.includes("#")) throw new TypeError("Application paths cannot contain fragments");

  const queryIndex = relativePath.indexOf("?");
  const pathname = queryIndex === -1 ? relativePath : relativePath.slice(0, queryIndex);
  if (pathname.startsWith("/") || pathname.startsWith("\\") || SCHEME.test(pathname)) {
    throw new TypeError("Application paths must be relative");
  }
  for (const segment of pathname.split("/")) {
    const decoded = fullyDecodeSegment(segment);
    if (decoded === "." || decoded === ".." || decoded.includes("/") || decoded.includes("\\")) {
      throw new TypeError("Application paths cannot escape their assigned root");
    }
    if (decoded.includes("\0")) throw new TypeError("Application paths cannot contain null bytes");
  }
  return relativePath;
}
