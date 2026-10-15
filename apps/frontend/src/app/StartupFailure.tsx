// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import styles from "./App.module.css";

/** Startup can fail before auth or Redux exists; retry starts a fresh configuration read. */
export default function StartupFailure() {
  const { t } = useTranslation();
  return (
    <main className={styles.startupFailure} role="alert">
      <p>{t("rework.manager.unavailable")}</p>
      <Button color="primary" variant="outlined" size="medium" onClick={() => window.location.reload()}>
        {t("rework.bootstrap.reload")}
      </Button>
    </main>
  );
}
