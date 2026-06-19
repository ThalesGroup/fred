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
 * Single source of truth for a team's identity colour, derived deterministically
 * from its name. The same colour is read everywhere a team appears — the sidebar
 * rail dot, the card avatar, and the card banner — so e.g. "fredlab" is green
 * everywhere with zero configuration. The day a team uploads a real logo it wins;
 * until then this default is the identity.
 */
export interface TeamColor {
  /** Saturated fill for the avatar tile. */
  solid: string;
  /** Readable text on the solid fill. */
  onSolid: string;
  /** Subtle gradient of the same hue for the card banner. */
  banner: string;
}

const WHITE = "var(--cold-grey-100)";

const hue = (name: string): TeamColor => ({
  solid: `var(--${name}-40)`,
  onSolid: WHITE,
  banner: `linear-gradient(135deg, var(--${name}-50), var(--${name}-30))`,
});

/** Team identity hues. `light-purple` is intentionally excluded — it is the
 *  brand-violet accent reserved for the personal space. */
const PALETTE: TeamColor[] = [hue("cold-green"), hue("mustard"), hue("indigo"), hue("light-blue"), hue("red")];

/** The personal space is NOT a team: a fixed brand-violet accent, never derived. */
export const PERSONAL_TEAM_COLOR: TeamColor = hue("light-purple");

/** Stable, well-distributed hash over the name's code points. */
function hashName(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

export function teamColor(name: string): TeamColor {
  return PALETTE[hashName(name) % PALETTE.length];
}
