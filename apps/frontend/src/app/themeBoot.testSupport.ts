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

import { readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";

export const BOOT_SCRIPT = readFileSync(path.resolve(__dirname, "../../public/theme-boot.js"), "utf8");

export function bootTheme(
  options: {
    storage?: Pick<Storage, "getItem">;
    prefersDark?: boolean;
    language?: string;
    now?: DateConstructor;
    timers?: Pick<Window, "setTimeout" | "clearTimeout">;
    hidden?: boolean;
  } = {},
) {
  const attributes: Record<string, string> = {};
  const properties: Record<string, string> = {};
  const element = {
    lang: "",
    setAttribute: (name: string, value: string) => (attributes[name] = value),
    style: { setProperty: (name: string, value: string) => (properties[name] = value) },
  };
  const document = Object.assign(new EventTarget(), {
    documentElement: element,
    hidden: options.hidden ?? false,
  });
  const window = Object.assign(
    new EventTarget(),
    { fredThemeClock: undefined as Window["fredThemeClock"] },
    options.timers ?? {
      setTimeout: () => 0,
      clearTimeout: () => {},
    },
    {
      localStorage: options.storage,
      matchMedia: options.prefersDark === undefined ? undefined : () => ({ matches: options.prefersDark }),
      navigator: options.language === undefined ? undefined : { language: options.language },
    },
  );
  runInNewContext(BOOT_SCRIPT, { window, document, Date: options.now ?? Date });
  return { attributes, properties, element, document, window, clock: window.fredThemeClock! };
}
