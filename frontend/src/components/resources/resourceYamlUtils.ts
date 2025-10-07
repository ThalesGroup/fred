// Copyright Thales 2025
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

import yaml from "js-yaml";

export type TemplateFormat = "markdown" | "html" | "text" | "json";

export const extractPlaceholders = (body: string) => {
  const re = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g;
  const vars = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) vars.add(m[1]);
  return Array.from(vars);
};

export const buildFrontMatter = (header: Record<string, any>, body: string): string => {
  const yamlHeader = Object.keys(header || {}).length ? yaml.dump(header, { lineWidth: 100 }).trim() : "";
  const cleanBody = (body ?? "").replace(/\r\n/g, "\n").trimEnd();
  return yamlHeader ? `${yamlHeader}\n---\n${cleanBody}` : cleanBody;
};

/** Detect if text looks like a front-matter doc (with or without opening ---). */
export const looksLikeYamlDoc = (text: string) => {
  const s = (text ?? "").replace(/\r\n/g, "\n").trimStart();
  if (s.startsWith("---\n")) return true;
  const sep = "\n---\n";
  const i = s.indexOf(sep);
  if (i === -1) return false;
  const head = s.slice(0, i);
  // header-ish if it contains at least one "key: value" line
  return /^[A-Za-z0-9_-]+\s*:\s?/m.test(head);
};

/** Split front-matter header + body.
 * Supports:
 *  A) Standard:  ---\nheader\n---\nbody
 *  B) No opening delimiter:  header\n---\nbody
 * If no header is found, returns { header: {}, body: text }.
 */
export const splitFrontMatter = (text: string): { header: Record<string, any>; body: string } => {
  const norm = (text ?? "").replace(/\r\n/g, "\n").trimStart();

  // Case A: standard front-matter with opening ---
  let m = norm.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  if (m) {
    const header = (yaml.load(m[1]) as Record<string, any>) ?? {};
    return { header, body: m[2] ?? "" };
  }

  // Case B: header at top, then a single '---' line
  const sep = "\n---\n";
  const i = norm.indexOf(sep);
  if (i !== -1) {
    const headBlock = norm.slice(0, i);
    // Only treat as header if it looks like YAML key/value lines
    if (/^[A-Za-z0-9_-]+\s*:\s?/m.test(headBlock)) {
      let header: Record<string, any> = {};
      try {
        header = (yaml.load(headBlock) as Record<string, any>) ?? {};
      } catch {
        header = {};
      }
      const body = norm.slice(i + sep.length);
      return { header, body };
    }
  }

  // Fallback: no header
  return { header: {}, body: norm };
};

/** NEW: Rebuild a prompt schema from the body placeholders. */
export const buildPromptSchemaFromBody = (body: string) => {
  const vars = extractPlaceholders(body || "");
  return {
    type: "object",
    required: vars,
    properties: Object.fromEntries(vars.map((v) => [v, { type: "string", title: v }])),
  };
};

/** NEW: Make a cleaned/upgraded header for PROMPT keeping extra keys unless overridden. */
export const normalizePromptHeader = (
  rawHeader: Record<string, any>,
  body: string,
  opts?: { keepVersion?: boolean; recomputeSchema?: boolean },
): Record<string, any> => {
  const keepVersion = opts?.keepVersion ?? true;
  const recomputeSchema = opts?.recomputeSchema ?? true;

  const header = { ...(rawHeader || {}) };

  // Enforce kind
  header.kind = "prompt";

  // Version policy in UI-only mode:
  if (!keepVersion || !header.version) {
    header.version = header.version || "v1";
  }

  // Optional: ensure known fields exist (don’t kill unknown ones)
  if (!("name" in header)) header.name = undefined;
  if (!("description" in header)) header.description = undefined;
  if (!("labels" in header)) header.labels = undefined;

  // Recompute schema from body placeholders if desired
  if (recomputeSchema) {
    header.schema = buildPromptSchemaFromBody(body);
  }

  return header;
};

/** NEW: For TEMPLATE (if you need it later) */
export const normalizeTemplateHeader = (
  rawHeader: Record<string, any>,
  body: string,
  format: TemplateFormat,
  opts?: { keepVersion?: boolean; recomputeSchema?: boolean },
) => {
  const h = normalizePromptHeader(rawHeader, body, opts);
  h.kind = "template";
  h.format = format;
  return h;
};

/* ===============================
 * PROFILE 
 * =============================== */

/** NEW: Rebuild a profile schema from the body placeholders (même logique que prompt). */
export const buildProfileSchemaFromBody = (body: string) => {
  const vars = extractPlaceholders(body || "");
  return {
    type: "object",
    required: vars,
    properties: Object.fromEntries(vars.map((v) => [v, { type: "string", title: v }])),
  };
};

/** NEW: Make a cleaned/upgraded header for PROFILE (mêmes règles que prompt). */
export const normalizeProfileHeader = (
  rawHeader: Record<string, any>,
  body: string,
  opts?: { keepVersion?: boolean; recomputeSchema?: boolean }
): Record<string, any> => {
  const keepVersion = opts?.keepVersion ?? true;
  const recomputeSchema = opts?.recomputeSchema ?? true;

  const header = { ...(rawHeader || {}) };

  // Enforce kind
  header.kind = "profile";

  // Version policy (par défaut v1)
  if (!keepVersion || !header.version) {
    header.version = header.version || "v1";
  }

  // Champs connus (ne supprime pas les clefs inconnues)
  if (!("name" in header)) header.name = undefined;
  if (!("description" in header)) header.description = undefined;
  if (!("labels" in header)) header.labels = undefined;

  // Schéma depuis les placeholders si demandé
  if (recomputeSchema) {
    header.schema = buildProfileSchemaFromBody(body);
  }

  return header;
};

/** NEW: Builder YAML pour PROFILE (copie de prompt avec kind=profile). */
export const buildProfileYaml = (opts: {
  name?: string | null;
  description?: string | null;
  labels?: string[] | null;
  body: string;
  version?: string; // default v1
}) => {
  const version = opts.version || "v1";
  const schema = buildProfileSchemaFromBody(opts.body);
  const header: Record<string, any> = {
    version,
    kind: "chat-context",
    name: opts.name || undefined,
    description: opts.description || undefined,
    schema,
  };
  return buildFrontMatter(header, opts.body);
};

// Existing builders (unchanged)
export const buildPromptYaml = (opts: {
  name?: string | null;
  description?: string | null;
  labels?: string[] | null;
  body: string;
  version?: string; // default v1
}) => {
  const version = opts.version || "v1";
  const schema = buildPromptSchemaFromBody(opts.body);
  const header: Record<string, any> = {
    version,
    kind: "prompt",
    name: opts.name || undefined,
    description: opts.description || undefined,
    schema,
  };
  return buildFrontMatter(header, opts.body);
};

export const buildTemplateYaml = (opts: {
  name?: string | null;
  description?: string | null;
  labels?: string[] | null;
  format: TemplateFormat;
  body: string;
  version?: string; // default v1
}) => {
  const version = opts.version || "v1";
  const schema = buildPromptSchemaFromBody(opts.body);
  const header: Record<string, any> = {
    version,
    kind: "template",
    name: opts.name || undefined,
    description: opts.description || undefined,
    format: opts.format,
    schema,
  };
  return buildFrontMatter(header, opts.body);
};
