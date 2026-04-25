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

import Button from "@shared/atoms/Button/Button.tsx";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import styles from "./GdprPage.module.css";

export default function GdprPage() {
  const { t } = useTranslation();

  return (
    <div className={styles.gdprContainer}>
      <div className={styles.gdprTitle}>{t("rework.gcu.title")}</div>
      <div className={styles.gdprContent}></div>
      <div className={styles.gdprActions}>
        <Link to={"/"}>
          <Button color={"primary"} variant={"filled"} size={"medium"}>
            {t("rework.gcu.backToApp")}
          </Button>
        </Link>
      </div>
    </div>
  );
}
