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

import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./PageError.module.css";

interface PageErrorProps {
  title?: string;
  message?: string;
}

export const PageError = ({ title = "Page Not Found", message = "Resource not found" }: PageErrorProps) => {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className={styles.page}>
      <span className={styles.icon}>
        <Icon category="outlined" type="error" filled />
      </span>
      <span className={styles.title}>{title}</span>
      <span className={styles.message}>{message}</span>
      <Button color="primary" variant="outlined" size="medium" onClick={() => navigate("/")}>
        {t("pageError.message")}
      </Button>
    </div>
  );
};
