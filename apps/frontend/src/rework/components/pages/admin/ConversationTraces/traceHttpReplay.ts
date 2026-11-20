// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { TraceHttpEvidence } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { traceBytes } from "./traceControls";

export const traceReplayFormats = ["python", "curl", "powershell"] as const;
type TraceReplayFormat = (typeof traceReplayFormats)[number];

type ReplayRequest = {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
};

type ReplayAvailability = { status: "ready"; request: ReplayRequest } | { status: "incomplete" | "unsupported" };

const legacyBearerTargets = new Set([
  "https://api.openai.com/v1/chat/completions",
  "https://api.openai.com/v1/responses",
  "https://api.mistral.ai/v1/chat/completions",
]);

export function prepareTraceHttpReplay(exchange: TraceHttpEvidence): ReplayAvailability {
  const { method, target, request_headers: headers, request_body: body } = exchange;
  if (!body?.complete) return { status: "incomplete" };
  const contentType = headers["content-type"];
  const encoding = headers["content-encoding"];
  try {
    const url = new URL(target);
    if (
      !(exchange.bearer_replay ?? legacyBearerTargets.has(target)) ||
      method !== "POST" ||
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      !/\/(?:chat\/completions|responses)\/?$/.test(url.pathname) ||
      contentType?.split(";", 1)[0].trim().toLowerCase() !== "application/json" ||
      (encoding && encoding.toLowerCase() !== "identity")
    ) {
      return { status: "unsupported" };
    }
    const replayHeaders: Record<string, string> = { "Content-Type": contentType };
    if (headers.accept) replayHeaders.Accept = headers.accept;
    if (!Object.values(replayHeaders).every((value) => /^[\x20-\x7e]+$/.test(value))) {
      return { status: "unsupported" };
    }
    const payload = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(traceBytes(body.data));
    if (payload.includes("\0")) return { status: "unsupported" };
    return { status: "ready", request: { url: target, method, headers: replayHeaders, body: payload } };
  } catch {
    return { status: "unsupported" };
  }
}

function pythonString(value: string): string {
  return "'" + JSON.stringify(value).slice(1, -1).replaceAll('\\"', '"').replaceAll("'", "\\'") + "'";
}

function pythonScript({ url, method, headers, body }: ReplayRequest): string {
  return [
    "from http.client import HTTPConnection, HTTPSConnection",
    "from pathlib import Path",
    "import sys",
    "from urllib.parse import urlsplit",
    "",
    "API_KEY = None",
    "URL = " + pythonString(url),
    "METHOD = " + pythonString(method),
    "HEADERS = " + JSON.stringify(headers),
    "BODY = " + pythonString(body),
    "",
    "def read_api_key():",
    '    env_path = Path(__file__).resolve().with_name(".env")',
    "    if env_path.is_file():",
    '        for line in env_path.read_text(encoding="utf-8-sig").splitlines():',
    '            name, sep, value = line.partition("=")',
    '            if sep and name.strip() == "OPENAI_API_KEY":',
    '                return value.strip().strip("\'\\\"")',
    "    return None",
    "",
    "",
    "api_key = API_KEY if API_KEY is not None else read_api_key()",
    "if not api_key:",
    '    sys.exit("Set API_KEY or add OPENAI_API_KEY to the .env file next to this script.")',
    "",
    "url = urlsplit(URL)",
    'connection_type = HTTPSConnection if url.scheme == "https" else HTTPConnection',
    "connection = connection_type(url.hostname, url.port, timeout=60)",
    'path = url.path or "/"',
    "if url.query:",
    '    path += "?" + url.query',
    "try:",
    '    headers = {**HEADERS, "Authorization": f"Bearer {api_key}"}',
    '    connection.request(METHOD, path, body=BODY.encode("utf-8"), headers=headers)',
    "    with connection.getresponse() as response:",
    '        print(f"HTTP {response.status}", flush=True)',
    "        for line in response:",
    "            sys.stdout.buffer.write(line)",
    "            sys.stdout.buffer.flush()",
    "finally:",
    "    connection.close()",
    "",
  ].join("\n");
}

const curlFlags = "--disable --silent --show-error --no-buffer --globoff --path-as-is";
const curlStatus = "\\nHTTP %{http_code}\\n";

function curlOptions({ url, method, headers }: ReplayRequest): [string, string][] {
  return [
    ["url", url],
    ["request", method],
    ...Object.entries(headers).map(([name, value]): [string, string] => ["header", name + ": " + value]),
    ["write-out", curlStatus],
  ];
}

function shellString(value: string): string {
  return "'" + value.replaceAll("'", "'\\''") + "'";
}

function curlCommand(request: ReplayRequest): string {
  return [
    "printf '%s' " + shellString(request.body) + " |",
    "  curl " + curlFlags + " \\",
    ...curlOptions(request).map(([name, value]) => "    --" + name + " " + shellString(value) + " \\"),
    '    --header "Authorization: Bearer ${OPENAI_API_KEY:?Set OPENAI_API_KEY for this URL}" \\',
    "    --data-binary @-",
    "",
  ].join("\n");
}

function powerShellCommand(request: ReplayRequest): string {
  // Use ASCII source and a UTF-8 file so Windows PowerShell keeps Unicode and exact line endings.
  const body = JSON.stringify({ body: request.body }).replace(/[^\x20-\x7e]/g, (character) => {
    return "\\u" + character.charCodeAt(0).toString(16).padStart(4, "0");
  });
  // curl reads quoted options from stdin, bypassing legacy PowerShell's native argument quoting.
  return [
    "& {",
    "  if (-not $env:OPENAI_API_KEY) { throw 'Set $env:OPENAI_API_KEY for this URL.' }",
    "  $body = (ConvertFrom-Json -InputObject @'",
    body,
    "'@).body",
    "  $options = @'",
    ...curlOptions(request).map(([name, value]) => name + " = " + JSON.stringify(value)),
    "'@",
    "  $bodyFile = [IO.Path]::GetTempFileName()",
    "  try {",
    "    [IO.File]::WriteAllText($bodyFile, $body, [Text.UTF8Encoding]::new($false))",
    "    $options | curl.exe " + curlFlags + " --config - " + "\x60",
    '      --header "Authorization: Bearer $env:OPENAI_API_KEY" --data-binary "@$bodyFile"',
    "  } finally {",
    "    Remove-Item -LiteralPath $bodyFile -Force",
    "  }",
    "}",
    "",
  ].join("\n");
}

const replayGenerators = { python: pythonScript, curl: curlCommand, powershell: powerShellCommand };

export function formatTraceHttpReplay(request: ReplayRequest, format: TraceReplayFormat): string {
  return replayGenerators[format](request);
}
