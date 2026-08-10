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

import { useTranslation } from "react-i18next";
import styles from "./HomePage.module.scss";

/**
 * Landing page behind the mainNavBar Home entry (`/home`). Placeholder for now
 * (#2298) — the team switcher lives in the Home nav panel to the left; this
 * content area will be filled in a follow-up.
 */
export default function HomePage() {
  const { t } = useTranslation();

  return (
    <div className={styles.page}>
      <span className={styles.title}>{t("rework.home.pageTitle")}</span>
      <span className={styles.subtitle}>{t("rework.home.pageSubtitle")}</span>
    </div>
  );
}
