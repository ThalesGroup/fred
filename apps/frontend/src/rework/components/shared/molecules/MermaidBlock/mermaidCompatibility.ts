// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

const ID = String.raw`[A-Za-z_][\w-]*`;
const NODE = String.raw`${ID}(?:\(\[[^\]]*\]\)|\(\([^)]*\)\)|\[[^\]]*\]|\([^)]*\)|\{[^}]*\})?(?:::\w+)?`;
const GROUP = String.raw`${NODE}(?:\s*&\s*${NODE})*`;
const LINK = String.raw`(?:-->|---|==>|-\.->)(?:\|[^|]*\|)?`;
const FLOW_LINE = new RegExp(String.raw`^${GROUP}(?:\s*${LINK}\s*${GROUP})*$`);
const FLOW_NODE = new RegExp(String.raw`^(${ID})(.*)$`);
const COMPLETE_NODE = new RegExp(`^${NODE}$`);
const FLOW_NODES = new RegExp(String.raw`(.+?)(\s*${LINK}\s*|\s*&\s*|$)`, "g");

/** Use the evaluated renderer subset; its parsers silently skip unknown statements. */
export function supportsBeautifulMermaid(code: string): boolean {
  const lines = code
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("%%"));
  const [header, ...body] = lines;
  if (!header || body.length === 0 || /;|`|@\{|%%\{|<(?!br\s*\/?\s*>|\|)/i.test(code)) return false;

  if (/^(?:graph|flowchart)\s+(?:TD|TB|LR|RL|BT)$/i.test(header)) {
    let depth = 0;
    const labels = new Map<string, string>();
    return (
      body.every((line) => {
        if (/^subgraph\s+[\w -]+(?:\[[^\]]+\])?$/.test(line)) {
          depth++;
          return true;
        }
        if (line === "end") return --depth >= 0;
        if (/^direction\s+(?:TD|TB|LR|RL|BT)$/.test(line)) return depth > 0;
        if (/^(?:classDef|class|style|linkStyle)\s+/.test(line)) return true;
        if (!FLOW_LINE.test(line)) return false;
        return [...line.matchAll(FLOW_NODES)].every(([, node, separator]) => {
          // Keep separators distinct from identifiers in the preferred parser.
          if (!COMPLETE_NODE.test(node) || (separator && !/^[\s&]/.test(separator))) return false;
          const parts = node.match(FLOW_NODE);
          if (!parts) return false;
          const [, id, label] = parts;
          // The preferred parser keeps the first label, while Mermaid permits later definitions.
          if (label && labels.has(id) && labels.get(id) !== label) return false;
          if (!labels.has(id)) labels.set(id, label);
          return true;
        });
      }) && depth === 0
    );
  }

  if (/^sequenceDiagram$/.test(header)) {
    let depth = 0;
    let declarationsEnded = false;
    const participants = new Set<string>();
    return (
      body.every((line) => {
        const declaration = line.match(/^(?:participant|actor)\s+(\w+)(?:\s+as\s+.+)?$/);
        if (declaration) {
          if (declarationsEnded || participants.has(declaration[1])) return false;
          participants.add(declaration[1]);
          return true;
        }
        declarationsEnded = true;
        if (/^(?:loop|alt|opt|par|critical|break|rect)\b/.test(line)) {
          depth++;
          return true;
        }
        if (line === "end") return --depth >= 0;
        if (/^(?:else|and)\b/.test(line)) return depth > 0;
        return (
          /^Note\s+(?:left of|right of|over)\s+[\w, ]+:\s*.+$/i.test(line) ||
          /^\w+\s*(?:->>|-->>|->|-->|-\)|--\))\s*[+-]?\w+\s*:\s*.+$/.test(line)
        );
      }) && depth === 0
    );
  }

  if (/^stateDiagram(?:-v2)?$/.test(header)) {
    const referenced = new Set<string>();
    return body.every((line) => {
      const alias = line.match(/^state\s+"[^"]+"\s+as\s+(\w+)$/);
      if (alias) {
        if (referenced.has(alias[1])) return false;
        referenced.add(alias[1]);
        return true;
      }
      const transition = line.match(/^(\[\*\]|[\w-]+)\s*-->\s*(\[\*\]|[\w-]+)(?:\s*:\s*.+)?$/);
      if (transition) {
        referenced.add(transition[1]);
        referenced.add(transition[2]);
        return true;
      }
      return /^direction\s+(?:TD|TB|LR|RL|BT)$/.test(line);
    });
  }

  if (/^classDiagram$/.test(header)) {
    let inClass = false;
    return (
      body.every((line) => {
        if (line === "}") {
          const open = inClass;
          inClass = false;
          return open;
        }
        if (inClass) return /^[+~#-]?[\w ~<>,()[\]:*$]+$/.test(line);
        if (/^class\s+\w+\s*\{$/.test(line)) {
          inClass = true;
          return true;
        }
        return (
          /^class\s+\w+$/.test(line) ||
          /^\w+\s*:\s*[+~#-]?[\w ~<>,()[\]:*$]+$/.test(line) ||
          /^\w+\s+(?:<\|--|--\|>|\*--|--\*|o--|--o|-->|<--|\.\.>|<\.\.|\.\.\|>|<\|\.\.|--)\s+\w+(?:\s*:\s*.+)?$/.test(
            line,
          )
        );
      }) && !inClass
    );
  }

  if (/^erDiagram$/.test(header)) {
    let inEntity = false;
    return (
      body.every((line) => {
        if (line === "}") {
          const open = inEntity;
          inEntity = false;
          return open;
        }
        if (inEntity) return /^\w+(?:\[\])?\s+\w+(?:\s+(?:PK|FK|UK))?(?:\s+"[^"]*")?$/.test(line);
        if (/^\w+\s*\{$/.test(line)) {
          inEntity = true;
          return true;
        }
        return /^\w+\s+(?:\|\||\|o|o\||\}\|)(?:--|\.\.)(?:\|\||o\||\|o|\|\{|o\{)\s+\w+\s*:\s*.+$/.test(line);
      }) && !inEntity
    );
  }

  if (/^xychart(?:-beta)?(?:\s+horizontal)?$/.test(header)) {
    return body.every(
      (line) =>
        /^title\s+"[^"]+"$/.test(line) ||
        /^(?:x-axis|y-axis)\s+(?:"[^"]*"\s*)?(?:\[[^\]]+\]|-?\d+(?:\.\d+)?\s*-->\s*-?\d+(?:\.\d+)?)$/.test(line) ||
        /^y-axis\s+"[^"]+"$/.test(line) ||
        /^(?:bar|line)\s+\[\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)*\s*\]$/.test(line),
    );
  }
  return false;
}
