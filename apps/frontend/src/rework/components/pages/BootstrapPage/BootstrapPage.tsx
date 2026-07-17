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

import { KeyboardEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useBootstrapPlatformAdminControlPlaneV1BootstrapPlatformAdminPostMutation } from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./BootstrapPage.module.css";

/** Mirrors the backend's `BootstrapPlatformAdminRequest.token` `min_length=16`. */
const MIN_TOKEN_LENGTH = 16;

/**
 * Pull an HTTP status and a FastAPI `detail` message out of an RTK Query
 * mutation error, matching the shape other mutations in this codebase read
 * (`error.data.detail`, `error.status`/`error.originalStatus`).
 */
const parseBootstrapError = (error: unknown): { status?: number; detail?: string } => {
  const err = error as { status?: number; originalStatus?: number; data?: { detail?: string } } | undefined;
  return {
    status: err?.status ?? err?.originalStatus,
    detail: err?.data?.detail,
  };
};

export default function BootstrapPage() {
  const { t } = useTranslation();
  const [token, setToken] = useState("");
  const [trigger, { isLoading, isSuccess, data, error, reset }] =
    useBootstrapPlatformAdminControlPlaneV1BootstrapPlatformAdminPostMutation();

  const { status, detail } = error ? parseBootstrapError(error) : { status: undefined, detail: undefined };
  // 409 means someone else (or another tab) completed bootstrap moments ago —
  // the flag is now global and permanent, so the only sane next step is to
  // reload: this page will stop being reachable once `BootstrapGuard` re-reads it.
  const isAlreadyCompleted = status === 409;

  // An invalid secret must not linger in the field: clear it so the user
  // can't accidentally resubmit the same wrong value, but keep the form on
  // screen so they can retry.
  useEffect(() => {
    if (status === 403) {
      setToken("");
    }
  }, [status]);

  const canSubmit = !isLoading && token.trim().length >= MIN_TOKEN_LENGTH;

  const handleSubmit = () => {
    if (!canSubmit) return;
    trigger({ bootstrapPlatformAdminRequest: { token } });
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      handleSubmit();
    }
  };

  if (isSuccess && data) {
    return (
      <div className={styles.bootstrapContainer}>
        <div className={styles.bootstrapTitle}>{t("rework.bootstrap.title")}</div>
        <div className={styles.bootstrapContent}>
          <p className={styles.bootstrapSuccessMessage}>
            {t("rework.bootstrap.successMessage", { username: data.username })}
          </p>
        </div>
        <div className={styles.bootstrapActions}>
          <Button color="primary" variant="filled" size="medium" onClick={() => window.location.reload()}>
            {t("rework.bootstrap.continue")}
          </Button>
        </div>
      </div>
    );
  }

  if (isAlreadyCompleted) {
    return (
      <div className={styles.bootstrapContainer}>
        <div className={styles.bootstrapTitle}>{t("rework.bootstrap.title")}</div>
        <div className={styles.bootstrapContent}>
          <p className={styles.bootstrapErrorMessage}>{t("rework.bootstrap.errors.alreadyCompleted")}</p>
        </div>
        <div className={styles.bootstrapActions}>
          <Button color="primary" variant="filled" size="medium" onClick={() => window.location.reload()}>
            {t("rework.bootstrap.reload")}
          </Button>
        </div>
      </div>
    );
  }

  // 403 gets a fixed, friendly copy (the backend's own detail for a wrong
  // secret is generic and not worth surfacing verbatim). 503 and anything
  // else fall back to the backend's own `detail` when present — for 503
  // ("auth or ReBAC disabled") that text is already accurate and actionable.
  const fieldError = status === 403 ? t("rework.bootstrap.errors.forbidden") : undefined;
  const generalError = error && status !== 403 ? detail || t("rework.bootstrap.errors.generic") : undefined;

  return (
    <div className={styles.bootstrapContainer}>
      <div className={styles.bootstrapTitle}>{t("rework.bootstrap.title")}</div>
      <div className={styles.bootstrapContent}>
        <p className={styles.bootstrapDescription}>{t("rework.bootstrap.description")}</p>
        <TextInput
          type="password"
          label={t("rework.bootstrap.tokenLabel")}
          placeholder={t("rework.bootstrap.tokenPlaceholder")}
          explanation={t("rework.bootstrap.tokenExplanation")}
          value={token}
          onChange={(event) => {
            if (error) reset();
            setToken(event.target.value);
          }}
          onKeyDown={handleKeyDown}
          minLength={MIN_TOKEN_LENGTH}
          required
          autoFocus
          disabled={isLoading}
          error={fieldError}
        />
        {generalError && <p className={styles.bootstrapErrorMessage}>{generalError}</p>}
      </div>
      <div className={styles.bootstrapActions}>
        <Button color="primary" variant="filled" size="medium" disabled={!canSubmit} onClick={handleSubmit}>
          {t("rework.bootstrap.submit")}
        </Button>
      </div>
    </div>
  );
}
