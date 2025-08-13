// resourceYaml.ts
// Lightweight YAML helpers shared by Prompt/Template editors.

import yaml from "js-yaml";
export type TemplateFormat = "markdown" | "html" | "text" | "json";

// Extract {placeholders} from a body string
export const extractPlaceholders = (body: string) => {
  const re = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g;
  const vars = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) vars.add(m[1]);
  return Array.from(vars);
};

// Serialize a simple front-matter header; uses inline JSON for nested values
export const buildFrontMatter1 = (header: Record<string, any>, body: string) => {
  const lines: string[] = [];
  for (const [k, v] of Object.entries(header)) {
    if (v === undefined || v === null || (Array.isArray(v) && v.length === 0)) continue;
    if (typeof v === "object") lines.push(`${k}: ${JSON.stringify(v)}`);
    else lines.push(`${k}: ${String(v)}`);
  }
  return `${lines.join("\n")}\n---\n${body ?? ""}`;
};
export const buildFrontMatter = (header: Record<string, any>, body: string): string => {
  const yamlHeader = yaml.dump(header).trim(); // pretty block-style YAML
  return `${yamlHeader}\n---\n${body?.trim() ?? ""}`;
};

// Heuristic: did the user paste a full YAML doc already?
export const looksLikeYamlDoc = (text: string) =>
  text.includes("\n---\n") && /^[A-Za-z0-9_-]+:\s/m.test(text);

// Build YAML for a PROMPT
export const buildPromptYaml = (opts: {
  name?: string | null;
  description?: string | null;
  labels?: string[] | null;
  body: string;
  version?: string; // default v1
}) => {
  const version = opts.version || "v1";
  const vars = extractPlaceholders(opts.body);

  const schema = {
    type: "object",
    required: vars,
    properties: Object.fromEntries(vars.map((v) => [v, { type: "string", title: v }])),
  };

  const header: Record<string, any> = {
    version,
    kind: "prompt",
    name: opts.name || undefined,
    description: opts.description || undefined,
    // tags: opts.labels && opts.labels.length ? opts.labels : undefined,
    schema,
  };

  return buildFrontMatter(header, opts.body);
};

// Build YAML for a TEMPLATE
export const buildTemplateYaml = (opts: {
  name?: string | null;
  description?: string | null;
  labels?: string[] | null;
  format: TemplateFormat;
  body: string;
  version?: string; // default v1
}) => {
  const version = opts.version || "v1";
  const vars = extractPlaceholders(opts.body);

  const schema = {
    type: "object",
    required: vars,
    properties: Object.fromEntries(vars.map((v) => [v, { type: "string", title: v }])),
  };

  const header: Record<string, any> = {
    version,
    kind: "template",
    name: opts.name || undefined,
    description: opts.description || undefined,
    format: opts.format,
    // tags: opts.labels && opts.labels.length ? opts.labels : undefined,
    schema,
  };

  return buildFrontMatter(header, opts.body);
};
