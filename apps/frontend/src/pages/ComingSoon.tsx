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

import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import styles from "./ComingSoon.module.css";

// Landing page for users rejected by the platform whitelist (HTTP 403
// "user_not_whitelisted", see docs/swift/platform/KEYCLOAK.md §"Behavior")
// and for any other "not available to you yet" bounce. Kept intentionally
// simple and dependency-light — it must render even when the rest of the
// app's bootstrap has failed.
export function ComingSoon() {
  const { t } = useTranslation();
  const { siteDisplayName, agentIconName } = useFrontendProperties();

  return (
    <div className={styles.container}>
      <img className={styles.icon} src={`images/${agentIconName}.svg`} alt="" />
      <p className={styles.title}>{t("comingSoon.title", { siteDisplayName })}</p>
      <p className={styles.description}>{t("comingSoon.description")}</p>
    </div>
  );
}
