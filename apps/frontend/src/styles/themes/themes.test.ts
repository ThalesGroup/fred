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

import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Every theme is a peer: same token set in each block, nothing inherited from
// the base stylesheets. Full rationale: FRONTEND_CODING_GUIDELINES.md (UI themes).
const THEMES_DIR = path.resolve(__dirname);
const STYLES_DIR = path.resolve(__dirname, "..");
const BLOCKS = ["root", "light", "dark"] as const;
type Block = (typeof BLOCKS)[number];

interface Rule {
  selector: string;
  body: string;
}

function parseRules(css: string): Rule[] {
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...withoutComments.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim(),
    body: m[2],
  }));
}

function customProperties(body: string): string[] {
  return [...body.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]);
}

function blockOf(selector: string, id: string): Block | undefined {
  if (selector === `:root[data-ui-theme="${id}"]`) return "root";
  if (selector === `[data-ui-theme="${id}"][data-theme="light"]`) return "light";
  if (selector === `[data-ui-theme="${id}"][data-theme="dark"]`) return "dark";
  return undefined;
}

function loadThemes(): Map<string, Map<Block, Rule>> {
  const themes = new Map<string, Map<Block, Rule>>();
  for (const file of readdirSync(THEMES_DIR).filter((f) => f.endsWith(".css"))) {
    const id = file.replace(/\.css$/, "");
    const blocks = new Map<Block, Rule>();
    for (const rule of parseRules(readFileSync(path.join(THEMES_DIR, file), "utf8"))) {
      const block = blockOf(rule.selector, id);
      if (!block) throw new Error(`${file}: unexpected selector "${rule.selector}"`);
      if (blocks.has(block)) throw new Error(`${file}: duplicate ${block} block`);
      blocks.set(block, rule);
    }
    themes.set(id, blocks);
  }
  return themes;
}

describe("UI themes", () => {
  const themes = loadThemes();

  it("ships at least the default theme", () => {
    expect([...themes.keys()]).toContain("pebble");
  });

  it("gives every theme a root, a light and a dark block", () => {
    for (const [id, blocks] of themes) {
      expect([...blocks.keys()].sort(), id).toEqual([...BLOCKS].sort());
    }
  });

  it("declares the same tokens in every theme and block", () => {
    const missing: string[] = [];
    for (const block of BLOCKS) {
      const union = new Set<string>();
      for (const blocks of themes.values()) customProperties(blocks.get(block)!.body).forEach((t) => union.add(t));
      for (const [id, blocks] of themes) {
        const declared = new Set(customProperties(blocks.get(block)!.body));
        for (const token of union) if (!declared.has(token)) missing.push(`${id} ${block} lacks ${token}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("declares the same colour tokens in light and dark", () => {
    for (const [id, blocks] of themes) {
      expect(customProperties(blocks.get("dark")!.body).sort(), id).toEqual(
        customProperties(blocks.get("light")!.body).sort(),
      );
    }
  });

  it("sets the matching color-scheme in each mode block", () => {
    for (const [id, blocks] of themes) {
      expect(blocks.get("light")!.body, id).toMatch(/color-scheme:\s*light/);
      expect(blocks.get("dark")!.body, id).toMatch(/color-scheme:\s*dark/);
    }
  });

  it("keeps theme tokens out of the base stylesheets", () => {
    const themeTokens = new Set<string>();
    for (const blocks of themes.values())
      for (const rule of blocks.values()) customProperties(rule.body).forEach((t) => themeTokens.add(t));
    const baseFiles = [
      ...readdirSync(STYLES_DIR)
        .filter((f) => /\.s?css$/.test(f))
        .map((f) => path.join(STYLES_DIR, f)),
      path.resolve(STYLES_DIR, "../styles.css"),
      path.resolve(STYLES_DIR, "../index.scss"),
    ];
    const leaks: string[] = [];
    for (const file of baseFiles) {
      for (const rule of parseRules(readFileSync(file, "utf8"))) {
        for (const token of customProperties(rule.body))
          if (themeTokens.has(token)) leaks.push(`${path.basename(file)} ${rule.selector} declares ${token}`);
      }
    }
    expect(leaks).toEqual([]);
  });
});
