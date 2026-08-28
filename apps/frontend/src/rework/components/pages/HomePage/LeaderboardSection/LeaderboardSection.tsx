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

import type { ReactNode } from "react";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { IconType } from "@shared/utils/Type.ts";
import styles from "./LeaderboardSection.module.scss";

interface LeaderboardSectionProps {
  icon: IconType;
  title: string;
  children: ReactNode;
}

/** Shared section shell for the home-page leaderboards (most-used agents,
 * most-active teams): an icon + title header over a single card. */
export default function LeaderboardSection({ icon, title, children }: LeaderboardSectionProps) {
  return (
    <section className={styles.section} aria-label={title}>
      <div className={styles.head}>
        <Icon category="outlined" type={icon} />
        <h2 className={styles.title}>{title}</h2>
      </div>
      <div className={styles.card}>{children}</div>
    </section>
  );
}
