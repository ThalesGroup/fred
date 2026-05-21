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

import { useState, useEffect } from "react";

/**
 * Reflects the current [data-theme] attribute on <html>.
 * Updates reactively when the user toggles the theme.
 */
export function useIsDark(): boolean {
  const [isDark, setIsDark] = useState(
    () => document.documentElement.dataset.theme === "dark",
  );

  useEffect(() => {
    const obs = new MutationObserver(() =>
      setIsDark(document.documentElement.dataset.theme === "dark"),
    );
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);

  return isDark;
}
