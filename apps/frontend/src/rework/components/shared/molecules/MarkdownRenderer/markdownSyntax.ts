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

import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import remarkDirective from "remark-directive";
import remarkParse from "remark-parse";
import { unified } from "unified";
import { makeReclaimUnknownDirectives } from "./markdownDirectives";

/** The syntax users can read in Fred; editing must not silently discard it. */
export const markdownSyntaxPlugins = [remarkMath, remarkGfm, remarkDirective];
const parser = unified().use(remarkParse).use(markdownSyntaxPlugins).use(makeReclaimUnknownDirectives());

export function hasSameMarkdownContent(before: string, after: string): boolean {
  const fingerprint = (source: string) =>
    JSON.stringify(parser.runSync(parser.parse(source)), (key, value) => {
      if (key === "position" || key === "spread") return undefined;
      if (key !== "children") return value;
      // Reclaimed directives can split one text run into adjacent text nodes.
      return value.reduce((nodes: Array<{ type: string; value?: string }>, node: { type: string; value?: string }) => {
        const last = nodes[nodes.length - 1];
        if (last?.type === "text" && node.type === "text")
          nodes[nodes.length - 1] = { ...last, value: (last.value ?? "") + (node.value ?? "") };
        else nodes.push(node);
        return nodes;
      }, []);
    });
  return fingerprint(before) === fingerprint(after);
}
