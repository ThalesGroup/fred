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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./FavoritesFilterChip.module.scss";

export interface FavoritesFilterChipProps {
  label: string;
  active: boolean;
  onToggle: () => void;
  /** "regular" sits among FilterChips; "xs" matches 32px fields (chat panel). */
  size?: "regular" | "xs";
}

/** Independent "favorites only" toggle. Filled in the warning colour when on,
 *  so it never reads as one more option of a radio chip group beside it. */
export default function FavoritesFilterChip({ label, active, onToggle, size = "regular" }: FavoritesFilterChipProps) {
  return (
    <button
      type="button"
      className={styles.chip}
      data-active={active}
      data-size={size}
      aria-pressed={active}
      onClick={onToggle}
    >
      <Icon category="outlined" type="star" filled />
      {label}
    </button>
  );
}
