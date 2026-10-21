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

import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";
import { cleanup, newRunScope } from "./runScope";

export type HeaderMap = Record<string, string>;

export interface SecurityDeps {
  origin: { https: boolean; local: boolean };
  /** Response headers of a same-origin GET, lower-cased; `token` adds a bearer. */
  headersOf: (path: string, token?: string) => Promise<{ status: number; headers: HeaderMap; body: string }>;
  token: () => Promise<string | null>;
  createLibrary: (name: string) => Promise<string>;
  deleteLibrary: (id: string) => Promise<void>;
  /** Ingests the file and returns its document uid. */
  ingest: (libraryId: string, file: File) => Promise<string>;
}

export const HARDENING_HEADERS = ["content-security-policy", "x-content-type-options", "referrer-policy"];
const ACTIVE_TYPES = ["image/svg+xml", "text/html", "application/xhtml+xml"];
const LEAKS = [/Traceback \(most recent call last\)/, /File "\/[^"]+\.py", line \d+/, /sqlalchemy\.exc\./i];

/** Whether a response can run script on the platform origin when opened as a document. */
export function runsActiveContent(headers: HeaderMap): boolean {
  const type = (headers["content-type"] ?? "").toLowerCase();
  const inline = !(headers["content-disposition"] ?? "").toLowerCase().startsWith("attachment");
  const sandboxed = (headers["content-security-policy"] ?? "").split(",").some((policy) => {
    const sandbox = policy
      .split(";")
      .map((directive) => directive.trim().toLowerCase().split(/\s+/))
      .find((tokens) => tokens[0] === "sandbox");
    return sandbox && (!sandbox.includes("allow-scripts") || !sandbox.includes("allow-same-origin"));
  });
  return inline && !sandboxed && ACTIVE_TYPES.some((t) => type.startsWith(t));
}

/** A harmless SVG: no script, only a marker; the check reads headers and never renders it. */
export function svgFixture(name: string, marker: string): File {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><title>${marker}</title></svg>`;
  return new File([svg], name, { type: "image/svg+xml" });
}

export const securityScenario: Scenario<SecurityDeps> = async (deps, report) => {
  const scope = newRunScope();
  let libraryId: string | null = null;

  await runStep(report, "transport", "The platform is served over HTTPS", async () => {
    if (deps.origin.https) return { value: undefined, detail: "https" };
    if (deps.origin.local) throw new SkipStep("plain HTTP on a local address");
    throw new Error("the platform is served over plain HTTP");
  });
  await runStep(
    report,
    "page-headers",
    "The page sets response-hardening headers",
    async () => {
      const { headers } = await deps.headersOf("/");
      const wanted = deps.origin.https ? [...HARDENING_HEADERS, "strict-transport-security"] : HARDENING_HEADERS;
      const framing = headers["x-frame-options"] || /frame-ancestors/i.test(headers["content-security-policy"] ?? "");
      const missing = [
        ...wanted.filter((h) => !headers[h]),
        ...(framing ? [] : ["x-frame-options or frame-ancestors"]),
      ];
      if (missing.length) throw new SkipStep(`not set by this deployment: ${missing.join(", ")}`);
      return { value: undefined, detail: "all present" };
    },
    { optional: true },
  );
  await runStep(report, "error-bodies", "Error responses expose no stack trace", async () => {
    const token = await deps.token();
    if (!token) throw new SkipStep("no session token");
    const probes = [
      `/knowledge-flow/v1/documents/metadata/${scope.name("missing")}`,
      `/control-plane/v1/teams/${scope.name("missing")}`,
      `/control-plane/v1/teams/${scope.name("missing")}/prompts/${scope.name("missing")}`,
    ];
    for (const path of probes) {
      const { status, body } = await deps.headersOf(path, token);
      if (status < 400) throw new Error(`${path} answered HTTP ${status} for an unknown id`);
      if (LEAKS.some((leak) => leak.test(body))) throw new Error(`${path} leaks server internals in its body`);
    }
    return { value: undefined, detail: `${probes.length} error bodies clean` };
  });

  try {
    const uid = await runStep(report, "upload-svg", "Upload an SVG document to your personal space", async () => {
      libraryId = await deps.createLibrary(scope.name("fred-selftest-security"));
      try {
        const id = await deps.ingest(libraryId, svgFixture(`${scope.name("fred-selftest")}.svg`, scope.token));
        return { value: id, detail: id };
      } catch (error) {
        throw new SkipStep(`this deployment does not ingest SVG (${(error as Error).message})`);
      }
    });
    await runStep(report, "download-attachment", "A raw download is served as an attachment", async () => {
      if (!uid) throw new SkipStep("no uploaded document");
      const token = await deps.token();
      const { status, headers } = await deps.headersOf(`/knowledge-flow/v1/raw_content/${uid}`, token ?? undefined);
      if (status !== 200) throw new Error(`download answered HTTP ${status}`);
      if (!(headers["content-disposition"] ?? "").toLowerCase().startsWith("attachment")) {
        throw new Error(`Content-Disposition is '${headers["content-disposition"] ?? "absent"}'`);
      }
      return { value: undefined, detail: headers["content-disposition"] };
    });
    await runStep(report, "inline-active-content", "Inline previews never serve runnable SVG or HTML", async () => {
      if (!uid) throw new SkipStep("no uploaded document");
      const token = await deps.token();
      const { status, headers } = await deps.headersOf(
        `/knowledge-flow/v1/raw_content/stream/${uid}`,
        token ?? undefined,
      );
      if (status !== 200 && status !== 206) throw new Error(`the preview answered HTTP ${status}`);
      if (runsActiveContent(headers)) {
        throw new Error(
          `served inline as ${headers["content-type"]} without an effective sandbox restriction: opened as a document, it would run on this origin`,
        );
      }
      return {
        value: undefined,
        detail: `${headers["content-type"] ?? "no type"}, ${headers["content-disposition"] ?? "no disposition"}`,
      };
    });
  } finally {
    await cleanup(
      report,
      "delete-security-folder",
      "Delete the security folder and its document",
      libraryId,
      deps.deleteLibrary,
    );
  }
};
