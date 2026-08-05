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

/**
 * Size of the layout viewport that `position: fixed` offsets are resolved
 * against. Never use `window.innerWidth`/`innerHeight` for popover math:
 * those include classic (non-overlay) scrollbars — the default on
 * Windows/Edge — while `position: fixed; bottom/right` exclude them, so a
 * portaled popover computed from `innerWidth`/`innerHeight` lands shifted by
 * the scrollbar thickness (~17px) whenever the document has a scrollbar.
 * `documentElement.clientWidth`/`clientHeight` match the fixed-position
 * containing block on every platform, and are identical to
 * `innerWidth`/`innerHeight` where scrollbars are overlay (Linux, macOS).
 */
export function viewportWidth(): number {
  return document.documentElement.clientWidth;
}

export function viewportHeight(): number {
  return document.documentElement.clientHeight;
}
