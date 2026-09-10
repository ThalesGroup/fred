import {
  FRED_APP_PROTOCOL_VERSION,
  parseApplicationFrameMessage,
  type ApplicationFrameMessage,
  type ApplicationHostMessage,
} from "@fred/iframe-sdk/protocol";

interface HostHarness {
  applicationOrigin: string;
  records: ApplicationFrameMessage[];
  rejected: number;
  readyCount: number;
  send(message: ApplicationHostMessage): void;
  sendRoute(subPath: string): void;
  configureContext(
    mode: "valid" | "malformed" | "mismatch" | "silent" | "unsupported",
    teamId?: string,
  ): void;
  replaceFrame(connectionTimeoutMs?: number): void;
}

declare global {
  interface Window {
    __fredHost: HostHarness;
  }
}

const parameters = new URLSearchParams(window.location.search);
const configuredApplicationOrigin = parameters.get("applicationOrigin");
const configuredAttackerOrigin = parameters.get("attackerOrigin");
if (!configuredApplicationOrigin || !configuredAttackerOrigin)
  throw new Error("fixture origins are required");
const applicationOrigin = configuredApplicationOrigin;
const attackerOrigin = configuredAttackerOrigin;

let applicationFrame =
  document.querySelector<HTMLIFrameElement>("#application")!;
const attackerFrame = document.querySelector<HTMLIFrameElement>("#attacker")!;
if (!applicationFrame || !attackerFrame)
  throw new Error("fixture frames are missing");
applicationFrame.src = `${applicationOrigin}/child.html?hostOrigin=${encodeURIComponent(window.location.origin)}`;
attackerFrame.src = `${attackerOrigin}/attacker.html?targetOrigin=${encodeURIComponent(applicationOrigin)}`;

const records: ApplicationFrameMessage[] = [];
let rejected = 0;
let readyCount = 0;
const pendingPair = new Map<string, string>();
let contextMode: "valid" | "malformed" | "mismatch" | "silent" | "unsupported" =
  "valid";
let contextTeamId = "team-1";

function applicationWindow(): Window {
  if (!applicationFrame.contentWindow)
    throw new Error("application frame is unavailable");
  return applicationFrame.contentWindow;
}

function send(message: ApplicationHostMessage): void {
  applicationWindow().postMessage(message, applicationOrigin);
}

function sendRaw(message: unknown): void {
  applicationWindow().postMessage(message, applicationOrigin);
}

function answerRequest(
  message: Extract<ApplicationFrameMessage, { type: "fred:request" }>,
): void {
  if (message.path.startsWith("pair/")) {
    pendingPair.set(message.path, message.requestId);
    if (pendingPair.size === 2) {
      for (const key of ["pair/two", "pair/one"]) {
        const requestId = pendingPair.get(key);
        if (requestId)
          send({
            type: "fred:response",
            requestId,
            status: 200,
            headers: {},
            body: key,
          });
      }
      pendingPair.clear();
    }
    return;
  }
  if (message.path === "transport-error") {
    send({ type: "fred:response-error", requestId: message.requestId });
    return;
  }
  if (message.path === "settlement/duplicate") {
    send({
      type: "fred:response",
      requestId: message.requestId,
      status: 200,
      headers: {},
      body: "first",
    });
    send({
      type: "fred:response",
      requestId: message.requestId,
      status: 200,
      headers: {},
      body: "duplicate",
    });
    return;
  }
  if (message.path === "settlement/unknown") {
    send({
      type: "fred:response",
      requestId: "unknown-request-id",
      status: 200,
      headers: {},
      body: "unknown",
    });
  }
  if (message.path === "pending/late") {
    window.setTimeout(
      () =>
        send({
          type: "fred:response",
          requestId: message.requestId,
          status: 200,
          headers: {},
          body: "late",
        }),
      50,
    );
    return;
  }
  if (message.path.startsWith("pending/")) return;
  const status = Number(message.path.match(/^status\/(\d+)$/)?.[1] ?? 200);
  send({
    type: "fred:response",
    requestId: message.requestId,
    status,
    headers: { "content-type": "application/json", "x-fred-fixture": "local" },
    body:
      [204, 205, 304].includes(status) || message.method === "HEAD"
        ? ""
        : JSON.stringify({ ok: status < 400 }),
  });
}

window.addEventListener("message", (event) => {
  if (
    event.source !== applicationFrame.contentWindow ||
    event.origin !== applicationOrigin
  ) {
    rejected += 1;
    return;
  }
  const message = parseApplicationFrameMessage(event.data);
  if (!message) {
    rejected += 1;
    return;
  }
  records.push(message);
  if (message.type === "fred:ready") {
    readyCount += 1;
    if (readyCount === 1) return;
    if (contextMode === "silent") return;
    if (contextMode === "malformed") {
      sendRaw({
        type: "fred:context",
        protocolVersion: FRED_APP_PROTOCOL_VERSION,
        applicationId: "example",
        context: { team: null },
      });
      return;
    }
    send({
      type: "fred:context",
      protocolVersion:
        contextMode === "unsupported" ? "2" : FRED_APP_PROTOCOL_VERSION,
      applicationId: contextMode === "mismatch" ? "other" : "example",
      context: {
        team: {
          id: contextTeamId,
          name: contextTeamId === "team-1" ? "Team One" : "Team Two",
          isPersonal: false,
        },
        route: {
          basePath: `/team/${contextTeamId}/apps/example`,
          subPath: "A",
        },
        locale: "en",
      },
    });
  } else if (message.type === "fred:request") {
    answerRequest(message);
  }
});

window.__fredHost = {
  applicationOrigin,
  records,
  get rejected() {
    return rejected;
  },
  get readyCount() {
    return readyCount;
  },
  send,
  sendRoute: (subPath) => send({ type: "fred:route", subPath }),
  configureContext: (mode, teamId = "team-1") => {
    contextMode = mode;
    contextTeamId = teamId;
  },
  replaceFrame: (connectionTimeoutMs) => {
    const replacement = applicationFrame.cloneNode(false) as HTMLIFrameElement;
    const replacementUrl = new URL(`${applicationOrigin}/child.html`);
    replacementUrl.searchParams.set("hostOrigin", window.location.origin);
    if (connectionTimeoutMs !== undefined)
      replacementUrl.searchParams.set(
        "connectionTimeoutMs",
        String(connectionTimeoutMs),
      );
    replacement.src = replacementUrl.href;
    applicationFrame.replaceWith(replacement);
    applicationFrame = replacement;
  },
};
