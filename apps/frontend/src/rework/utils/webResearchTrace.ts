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

// Native web research tools (fred-capability-web-research). Their query and
// public URL are user-facing by design, so the trace may show them.

export type WebResearchToolKind = "webSearch" | "fetchUrl";

export type WebResearchPage = {
  url: string;
  title: string;
  snippet: string;
  content: string | null;
  truncated: boolean;
  errorCode: string | null;
};

export type WebResearchTraceResult = { kind: "pages"; pages: WebResearchPage[] } | { kind: "error"; errorCode: string };

const TOOL_KINDS: Record<string, WebResearchToolKind> = {
  web_search: "webSearch",
  fetch_url: "fetchUrl",
};

export function webResearchToolKind(name: string): WebResearchToolKind | null {
  return TOOL_KINDS[name] ?? null;
}

const str = (value: unknown): string => (typeof value === "string" ? value : "");

/** The query or URL the call targeted, for the trace row and drawer header. */
export function webResearchTarget(kind: WebResearchToolKind, args: Record<string, unknown>): string {
  return kind === "fetchUrl" ? str(args.url) : str(args.query);
}

export function parseWebResearchResult(content: string): WebResearchTraceResult | null {
  let data: unknown;
  try {
    data = JSON.parse(content);
  } catch {
    return null;
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const record = data as Record<string, unknown>;
  if (typeof record.error_code === "string") return { kind: "error", errorCode: record.error_code };
  if (!Array.isArray(record.results)) return null;
  const pages = record.results
    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    .map((item) => ({
      url: str(item.final_url) || str(item.url),
      title: str(item.title),
      snippet: str(item.snippet),
      content: typeof item.content === "string" ? item.content : null,
      truncated: item.truncated === true,
      errorCode: typeof item.error_code === "string" ? item.error_code : null,
    }));
  return { kind: "pages", pages };
}
