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

import { isRouteErrorResponse, useNavigate, useRouteError } from "react-router-dom";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./PageError.module.css";

interface PageErrorProps {
  title?: string;
  message?: string;
  actions?: ReactNode;
  illustration?: ReactNode;
}

function DefaultErrorAction() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  return (
    <Button color="primary" variant="outlined" size="medium" onClick={() => navigate("/")}>
      {t("pageError.message")}
    </Button>
  );
}

export const PageError = ({
  title = "Page Not Found",
  message = "Resource not found",
  actions,
  illustration,
}: PageErrorProps) => {
  return (
    <div className={styles.page} role="region" aria-label={title} data-shell-scroll="contained">
      <span className={styles.icon}>{illustration ?? <Icon category="outlined" type="error" filled />}</span>
      <h1 className={styles.title}>{title}</h1>
      <span className={styles.message} role="alert">
        {message}
      </span>
      {actions ?? <DefaultErrorAction />}
    </div>
  );
};

export function RouteError() {
  const { t } = useTranslation();
  const error = useRouteError();
  const details = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.stack || error.message
      : typeof error === "string"
        ? error
        : undefined;

  return (
    <main className={styles.routeError}>
      <div className={styles.routeCard}>
        <PageError
          title={t("pageError.routeTitle")}
          message={t("pageError.routeDescription")}
          illustration={
            <svg className={styles.routeSketch} viewBox="0 0 280 120" fill="none" aria-hidden="true">
              <path
                d="M18 78c31 0 27-53 61-53 35 0 8 72 42 72 35 0 17-61 46-61 25 0 16 33 37 33"
                stroke="currentColor"
                strokeWidth="7"
                strokeLinecap="round"
              />
              <rect
                x="204"
                y="55"
                width="26"
                height="28"
                rx="6"
                fill="var(--surface-container-high)"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path d="M230 62h11m-11 14h11" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
              <path d="m253 49 4-7m0 21 9-2m-16 11 6 6" stroke="var(--error)" strokeWidth="3" strokeLinecap="round" />
              <circle cx="38" cy="39" r="4" fill="var(--error)" />
            </svg>
          }
          actions={
            <div className={styles.routeActions}>
              <Button color="primary" variant="filled" size="medium" onClick={() => window.location.reload()}>
                {t("pageError.retry")}
              </Button>
              <DefaultErrorAction />
            </div>
          }
        />
        {details && (
          <details className={styles.routeDetails}>
            <summary>{t("pageError.technicalDetails")}</summary>
            <pre>{details}</pre>
          </details>
        )}
      </div>
    </main>
  );
}
