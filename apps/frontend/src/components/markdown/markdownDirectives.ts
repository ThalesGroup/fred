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

import type { Plugin } from "unified";
import { visit } from "unist-util-visit";

/**
 * remark-directive parses a bare `:name` / `::name` as a text/leaf directive, so plain
 * prose containing something like an Excel range `D4:D5` gets misparsed — the `:D5` is
 * consumed as an unrecognized directive and silently dropped instead of rendered.
 *
 * This plugin must run after every directive-consuming plugin in the pipeline. It walks
 * the mdast and turns any text/leaf directive whose name is NOT in `whitelist` back into
 * its literal source text. Container directives (`:::name`) are left untouched — they
 * require three colons in a row, so they are not the source of the accidental-colon
 * problem.
 */
export function makeReclaimUnknownDirectives(whitelist: Iterable<string> = []): Plugin {
  const known = new Set(whitelist);

  return () => (tree: any) => {
    visit(tree, (node: any, index: number | null, parent: any) => {
      if (index == null || !parent) return;
      if (node.type !== "textDirective" && node.type !== "leafDirective") return;
      if (known.has(node.name)) return;

      const marker = node.type === "leafDirective" ? "::" : ":";
      let raw = `${marker}${node.name}`;

      const label = node.children?.map((c: any) => c.value ?? "").join("") ?? "";
      if (label) raw += `[${label}]`;

      const attrEntries = Object.entries(node.attributes ?? {}).filter(([, v]) => v != null);
      if (attrEntries.length) {
        raw += `{${attrEntries.map(([k, v]) => (v === "" ? String(k) : `${k}="${v}"`)).join(" ")}}`;
      }

      parent.children[index] = { type: "text", value: raw };
    });
  };
}
