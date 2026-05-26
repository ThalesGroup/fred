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

import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import ReleaseNotesContent from "./ReleaseNotesContent";
import styles from "./ReleaseNotesPage.module.css";

export default function ReleaseNotesPage() {
  const { t } = useTranslation();

  return (
    <div className={styles.releaseNotesContainer}>
      <div className={styles.releaseNotesHeader}>
        <Link to={"/"}>
          <Button
            color={"primary"}
            variant={"text"}
            size={"medium"}
            icon={{ category: "outlined", type: "arrow_back", filled: true }}
          >
            {t("rework.back")}
          </Button>
        </Link>
        <span className={styles.releaseNotesTitle}>{t("rework.userSettings.accessReleaseNotes")}</span>
      </div>
      <div className={styles.releaseNotesContent}>
        <ReleaseNotesContent />
      </div>
    </div>
  );
}
