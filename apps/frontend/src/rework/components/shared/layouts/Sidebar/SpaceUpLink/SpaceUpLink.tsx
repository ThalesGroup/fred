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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./SpaceUpLink.module.css";

export interface SpaceUpLinkProps {
  name: string;
  kind: "organization" | "team";
  onClick: () => void;
}

/** Quiet link on top of a nav panel, up to the parent space (as in the organization mockups). */
export default function SpaceUpLink({ name, kind, onClick }: SpaceUpLinkProps) {
  const { t } = useTranslation();
  return (
    <span className={styles.container}>
      <button type="button" className={styles.link} onClick={onClick} aria-label={t("rework.backTo", { name })}>
        <span className={styles.chevron}>
          <Icon category="outlined" type="chevron_left" />
        </span>
        <span className={styles.kind}>
          <Icon category="outlined" type={kind === "organization" ? "domain" : "groups"} />
        </span>
        <span className={styles.label} title={name}>
          {name}
        </span>
      </button>
    </span>
  );
}
