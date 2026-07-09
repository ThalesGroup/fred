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

interface MdastNode {
  type: string;
  name?: string;
  value?: string;
  attributes?: Record<string, string | null | undefined>;
  children?: MdastNode[];
}

/**
 * remark-directive parses a bare `:name` / `::name` as a text/leaf directive, so plain
 * prose containing something like an Excel range `D4:D5` gets misparsed — the `:D5` is
 * consumed as an unrecognized directive and silently dropped instead of rendered.
 *
 * Must run after remarkDirective and remarkDetailsDirective in the pipeline. Turns any
 * text/leaf directive whose name is NOT in `whitelist` back into its literal source text.
 * Container directives (`:::name`) are left untouched — they aren't the source of the
 * accidental-colon problem.
 */
export function makeReclaimUnknownDirectives(whitelist: Iterable<string> = []) {
  const known = new Set(whitelist);

  function reclaim(node: MdastNode) {
    if (!Array.isArray(node.children)) return;
    node.children = node.children.map((child) => {
      if ((child.type === "textDirective" || child.type === "leafDirective") && !known.has(child.name ?? "")) {
        return toLiteralTextNode(child);
      }
      reclaim(child);
      return child;
    });
  }

  return () => (tree: MdastNode) => {
    reclaim(tree);
  };
}

function toLiteralTextNode(node: MdastNode): MdastNode {
  const marker = node.type === "leafDirective" ? "::" : ":";
  let raw = `${marker}${node.name}`;

  const label = node.children?.map((c) => c.value ?? "").join("") ?? "";
  if (label) raw += `[${label}]`;

  const attrEntries = Object.entries(node.attributes ?? {}).filter(([, v]) => v != null);
  if (attrEntries.length) {
    raw += `{${attrEntries.map(([k, v]) => (v === "" ? String(k) : `${k}="${v}"`)).join(" ")}}`;
  }

  return { type: "text", value: raw };
}
