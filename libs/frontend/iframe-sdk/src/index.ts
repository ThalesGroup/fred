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
  APPLICATION_REQUEST_METHODS,
  FRED_APP_PROTOCOL_VERSION,
  MAX_APPLICATION_REQUEST_HEADERS,
  MAX_APPLICATION_REQUEST_ID_LENGTH,
  MAX_PENDING_APPLICATION_REQUESTS,
  isProtectedApplicationHeader,
  normalizeApplicationRelativePath,
  parseApplicationHostMessage,
  type ApplicationFrameMessage,
  type ApplicationRequestMethod,
  type FredApplicationContext,
  type FredApplicationRoute,
} from "../.generated/applicationProtocol.ts";

export type {
  FredApplicationContext,
  FredApplicationRoute,
} from "../.generated/applicationProtocol.ts";

export type FredApplicationClientErrorCode =
  | "invalid-configuration"
  | "missing-parent"
  | "connection-timeout"
  | "malformed-context"
  | "unsupported-protocol"
  | "application-mismatch"
  | "not-connected"
  | "invalid-request"
  | "request-capacity"
  | "request-timeout"
  | "transport-error"
  | "disposed";

export class FredApplicationClientError extends Error {
  readonly code: FredApplicationClientErrorCode;

  constructor(code: FredApplicationClientErrorCode, message: string) {
    super(message);
    this.name = "FredApplicationClientError";
    this.code = code;
  }
}

export interface FredApplicationClientOptions {
  hostOrigin: string;
  applicationId: string;
  connectionTimeoutMs?: number;
  requestTimeoutMs?: number;
}

export interface FredApplicationRequestInit {
  method?: ApplicationRequestMethod;
  headers?: HeadersInit;
  body?: string | null;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface FredApplicationClient {
  readonly context: FredApplicationContext | null;
  connect(): Promise<FredApplicationContext>;
  onRoute(listener: (route: FredApplicationRoute) => void): () => void;
  navigate(path: string, options?: { replace?: boolean }): void;
  openChat(sessionId?: string | null): void;
  request(path: string, init?: FredApplicationRequestInit): Promise<Response>;
  dispose(): void;
}

interface PendingRequest {
  method: ApplicationRequestMethod;
  resolve: (response: Response) => void;
  reject: (reason: unknown) => void;
  timer: ReturnType<typeof setTimeout>;
  signal?: AbortSignal;
  abort?: () => void;
}

type ClientState = "idle" | "connecting" | "connected" | "failed" | "disposed";

const DEFAULT_CONNECTION_TIMEOUT_MS = 10_000;
const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;
const READY_RETRY_MS = 500;

function clientError(
  code: FredApplicationClientErrorCode,
  message: string,
): FredApplicationClientError {
  return new FredApplicationClientError(code, message);
}

function positiveTimeout(
  value: number | undefined,
  fallback: number,
  field: string,
): number {
  const resolved = value ?? fallback;
  if (!Number.isFinite(resolved) || resolved <= 0) {
    throw clientError(
      "invalid-configuration",
      `${field} must be a positive finite number`,
    );
  }
  return resolved;
}

function configuredOrigin(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw clientError(
      "invalid-configuration",
      "hostOrigin must be an absolute HTTP(S) origin",
    );
  }
  if (
    (url.protocol !== "http:" && url.protocol !== "https:") ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw clientError(
      "invalid-configuration",
      "hostOrigin must be an absolute HTTP(S) origin",
    );
  }
  return url.origin;
}

function freezeContext(
  context: FredApplicationContext,
): FredApplicationContext {
  Object.freeze(context.team);
  Object.freeze(context.route);
  return Object.freeze(context);
}

function randomUuid(crypto: Crypto): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hexadecimal = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `${hexadecimal.slice(0, 8)}-${hexadecimal.slice(8, 12)}-${hexadecimal.slice(12, 16)}-${hexadecimal.slice(16, 20)}-${hexadecimal.slice(20)}`;
}

class FredApplicationClientImplementation implements FredApplicationClient {
  readonly #hostOrigin: string;
  readonly #applicationId: string;
  readonly #connectionTimeoutMs: number;
  readonly #requestTimeoutMs: number;
  readonly #childWindow: Window;
  readonly #parentWindow: Window;
  readonly #subscribers = new Set<(route: FredApplicationRoute) => void>();
  readonly #pending = new Map<string, PendingRequest>();
  #state: ClientState = "idle";
  #context: FredApplicationContext | null = null;
  #connectionPromise?: Promise<FredApplicationContext>;
  #resolveConnection?: (context: FredApplicationContext) => void;
  #rejectConnection?: (reason: unknown) => void;
  #readyTimer?: ReturnType<typeof setInterval>;
  #connectionTimer?: ReturnType<typeof setTimeout>;
  #listening = false;

  constructor(options: FredApplicationClientOptions) {
    if (!options || typeof options !== "object") {
      throw clientError("invalid-configuration", "client options are required");
    }
    this.#hostOrigin = configuredOrigin(options.hostOrigin);
    if (
      typeof options.applicationId !== "string" ||
      !options.applicationId.trim()
    ) {
      throw clientError(
        "invalid-configuration",
        "applicationId must be a non-empty string",
      );
    }
    this.#applicationId = options.applicationId;
    this.#connectionTimeoutMs = positiveTimeout(
      options.connectionTimeoutMs,
      DEFAULT_CONNECTION_TIMEOUT_MS,
      "connectionTimeoutMs",
    );
    this.#requestTimeoutMs = positiveTimeout(
      options.requestTimeoutMs,
      DEFAULT_REQUEST_TIMEOUT_MS,
      "requestTimeoutMs",
    );
    if (typeof window === "undefined")
      throw clientError("missing-parent", "the SDK requires a browser window");
    this.#childWindow = window;
    this.#parentWindow = window.parent;
    if (!this.#parentWindow || this.#parentWindow === window) {
      throw clientError(
        "missing-parent",
        "the SDK must run inside an iframe with a parent window",
      );
    }
  }

  get context(): FredApplicationContext | null {
    return this.#context;
  }

  connect(): Promise<FredApplicationContext> {
    if (this.#state === "disposed")
      return Promise.reject(clientError("disposed", "the client is disposed"));
    if (this.#connectionPromise) return this.#connectionPromise;
    this.#state = "connecting";
    this.#connectionPromise = new Promise((resolve, reject) => {
      this.#resolveConnection = resolve;
      this.#rejectConnection = reject;
    });
    this.#listen();
    try {
      this.#post({
        type: "fred:ready",
        protocolVersion: FRED_APP_PROTOCOL_VERSION,
      });
    } catch (error) {
      this.#failConnection(this.#transportError(error));
      return this.#connectionPromise;
    }
    this.#readyTimer = setInterval(() => {
      try {
        this.#post({
          type: "fred:ready",
          protocolVersion: FRED_APP_PROTOCOL_VERSION,
        });
      } catch (error) {
        this.#failConnection(this.#transportError(error));
      }
    }, READY_RETRY_MS);
    this.#connectionTimer = setTimeout(
      () =>
        this.#failConnection(
          clientError(
            "connection-timeout",
            "the FRED host did not provide context before the deadline",
          ),
        ),
      this.#connectionTimeoutMs,
    );
    return this.#connectionPromise;
  }

  onRoute(listener: (route: FredApplicationRoute) => void): () => void {
    this.#requireConnected();
    if (typeof listener !== "function")
      throw new TypeError("route listener must be a function");
    this.#subscribers.add(listener);
    return () => this.#subscribers.delete(listener);
  }

  navigate(path: string, options: { replace?: boolean } = {}): void {
    this.#requireConnected();
    this.#post({
      type: "fred:navigate",
      path: normalizeApplicationRelativePath(path),
      replace: options.replace === true,
    });
  }

  openChat(sessionId?: string | null): void {
    this.#requireConnected();
    this.#post({
      type: "fred:open-chat",
      sessionId: typeof sessionId === "string" && sessionId ? sessionId : null,
    });
  }

  request(
    path: string,
    init: FredApplicationRequestInit = {},
  ): Promise<Response> {
    this.#requireConnected();
    const normalizedPath = normalizeApplicationRelativePath(path);
    const method = init.method ?? "GET";
    if (!(APPLICATION_REQUEST_METHODS as readonly string[]).includes(method)) {
      return Promise.reject(
        clientError(
          "invalid-request",
          `unsupported request method: ${String(method)}`,
        ),
      );
    }
    if (
      init.body !== undefined &&
      init.body !== null &&
      typeof init.body !== "string"
    ) {
      return Promise.reject(
        clientError("invalid-request", "request body must be a string or null"),
      );
    }
    const headers = new Headers(init.headers);
    if ([...headers].length > MAX_APPLICATION_REQUEST_HEADERS) {
      return Promise.reject(
        clientError(
          "invalid-request",
          `requests may include at most ${MAX_APPLICATION_REQUEST_HEADERS} headers`,
        ),
      );
    }
    for (const [name] of headers) {
      if (isProtectedApplicationHeader(name)) {
        return Promise.reject(
          clientError(
            "invalid-request",
            `application requests cannot set the ${name} header`,
          ),
        );
      }
    }
    if (this.#pending.size >= MAX_PENDING_APPLICATION_REQUESTS) {
      return Promise.reject(
        clientError(
          "request-capacity",
          "the client already has 16 pending requests",
        ),
      );
    }
    if (init.signal?.aborted)
      return Promise.reject(
        new DOMException("The operation was aborted", "AbortError"),
      );
    const timeoutMs = positiveTimeout(
      init.timeoutMs,
      this.#requestTimeoutMs,
      "timeoutMs",
    );
    const requestId = this.#requestId();
    return new Promise<Response>((resolve, reject) => {
      const pending: PendingRequest = {
        method,
        resolve,
        reject,
        timer: setTimeout(
          () =>
            this.#rejectPending(
              requestId,
              clientError(
                "request-timeout",
                "the request exceeded its local deadline",
              ),
            ),
          timeoutMs,
        ),
        signal: init.signal,
      };
      if (init.signal) {
        pending.abort = () =>
          this.#rejectPending(
            requestId,
            new DOMException("The operation was aborted", "AbortError"),
          );
        init.signal.addEventListener("abort", pending.abort, { once: true });
      }
      this.#pending.set(requestId, pending);
      try {
        this.#post({
          type: "fred:request",
          requestId,
          path: normalizedPath,
          method,
          headers: Object.fromEntries(headers),
          body: typeof init.body === "string" ? init.body : null,
        });
      } catch (error) {
        this.#rejectPending(requestId, error);
      }
    });
  }

  dispose(): void {
    if (this.#state === "disposed") return;
    const error = clientError("disposed", "the client is disposed");
    if (this.#state === "connecting") this.#rejectConnection?.(error);
    this.#state = "disposed";
    this.#stopConnectionTimers();
    for (const requestId of [...this.#pending.keys()])
      this.#rejectPending(requestId, error);
    this.#subscribers.clear();
    if (this.#listening)
      this.#childWindow.removeEventListener("message", this.#onMessage);
    this.#listening = false;
  }

  readonly #onMessage = (event: MessageEvent): void => {
    if (
      event.source !== this.#parentWindow ||
      event.origin !== this.#hostOrigin
    )
      return;
    const message = parseApplicationHostMessage(event.data);
    if (!message) {
      if (
        this.#state === "connecting" &&
        this.#messageType(event.data) === "fred:context"
      ) {
        this.#failConnection(
          clientError(
            "malformed-context",
            "the FRED host sent malformed application context",
          ),
        );
      }
      return;
    }
    if (message.type === "fred:context") {
      if (this.#state !== "connecting") return;
      if (message.protocolVersion !== FRED_APP_PROTOCOL_VERSION) {
        this.#failConnection(
          clientError(
            "unsupported-protocol",
            `unsupported FRED application protocol: ${message.protocolVersion}`,
          ),
        );
        return;
      }
      if (message.applicationId !== this.#applicationId) {
        this.#failConnection(
          clientError(
            "application-mismatch",
            "the FRED host context names a different application",
          ),
        );
        return;
      }
      this.#context = freezeContext(message.context);
      this.#state = "connected";
      this.#stopConnectionTimers();
      this.#resolveConnection?.(this.#context);
      return;
    }
    if (this.#state !== "connected") return;
    if (message.type === "fred:route") {
      const route = Object.freeze({ subPath: message.subPath });
      for (const subscriber of [...this.#subscribers]) {
        try {
          subscriber(route);
        } catch (error) {
          globalThis.reportError?.(error);
        }
      }
      return;
    }
    const pending = this.#pending.get(message.requestId);
    if (!pending) return;
    if (message.type === "fred:response-error") {
      this.#clearPending(message.requestId, pending);
      pending.reject(
        clientError(
          "transport-error",
          "the FRED host could not complete the application request",
        ),
      );
      return;
    }
    const body =
      pending.method === "HEAD" || [204, 205, 304].includes(message.status)
        ? null
        : new TextEncoder().encode(message.body);
    let response: Response;
    try {
      response = new Response(body, {
        status: message.status,
        headers: message.headers,
      });
    } catch {
      this.#rejectPending(
        message.requestId,
        clientError(
          "transport-error",
          "the FRED host sent an invalid application response",
        ),
      );
      return;
    }
    this.#clearPending(message.requestId, pending);
    pending.resolve(response);
  };

  #listen(): void {
    if (this.#listening) return;
    this.#childWindow.addEventListener("message", this.#onMessage);
    this.#listening = true;
  }

  #post(message: ApplicationFrameMessage): void {
    try {
      this.#parentWindow.postMessage(message, this.#hostOrigin);
    } catch {
      throw clientError(
        "transport-error",
        "the client could not post a message to the FRED host",
      );
    }
  }

  #transportError(error: unknown): FredApplicationClientError {
    return error instanceof FredApplicationClientError
      ? error
      : clientError(
          "transport-error",
          "the client could not post a message to the FRED host",
        );
  }

  #requireConnected(): void {
    if (this.#state === "disposed")
      throw clientError("disposed", "the client is disposed");
    if (this.#state !== "connected")
      throw clientError(
        "not-connected",
        "connect must resolve before using the client",
      );
  }

  #messageType(value: unknown): unknown {
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as { type?: unknown }).type
      : undefined;
  }

  #requestId(): string {
    for (let attempt = 0; attempt < 100; attempt += 1) {
      let requestId: string;
      try {
        requestId = randomUuid(this.#childWindow.crypto);
      } catch {
        throw clientError(
          "invalid-request",
          "secure random request IDs are unavailable",
        );
      }
      if (
        requestId.length <= MAX_APPLICATION_REQUEST_ID_LENGTH &&
        !this.#pending.has(requestId)
      )
        return requestId;
    }
    throw clientError(
      "invalid-request",
      "could not allocate a unique request ID",
    );
  }

  #failConnection(error: FredApplicationClientError): void {
    if (this.#state !== "connecting") return;
    this.#state = "failed";
    this.#stopConnectionTimers();
    this.#rejectConnection?.(error);
    if (this.#listening)
      this.#childWindow.removeEventListener("message", this.#onMessage);
    this.#listening = false;
  }

  #stopConnectionTimers(): void {
    if (this.#readyTimer) clearInterval(this.#readyTimer);
    if (this.#connectionTimer) clearTimeout(this.#connectionTimer);
    this.#readyTimer = undefined;
    this.#connectionTimer = undefined;
  }

  #clearPending(requestId: string, pending: PendingRequest): void {
    clearTimeout(pending.timer);
    if (pending.signal && pending.abort)
      pending.signal.removeEventListener("abort", pending.abort);
    this.#pending.delete(requestId);
  }

  #rejectPending(requestId: string, reason: unknown): void {
    const pending = this.#pending.get(requestId);
    if (!pending) return;
    this.#clearPending(requestId, pending);
    pending.reject(reason);
  }
}

export function createFredApplicationClient(
  options: FredApplicationClientOptions,
): FredApplicationClient {
  return new FredApplicationClientImplementation(options);
}
