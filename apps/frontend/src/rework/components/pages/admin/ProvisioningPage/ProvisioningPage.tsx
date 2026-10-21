// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import FileDropzone from "@shared/molecules/FileDropzone/FileDropzone";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { useImportBlueprintMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./ProvisioningPage.module.css";

export default function ProvisioningPage() {
  const { t } = useTranslation();
  const access = useManagerPlatformAdmin();
  const [file, setFile] = useState<File | null>(null);
  const [importBlueprint, result] = useImportBlueprintMutation();
  const submitting = useRef(false);
  const error = result.error ? normalizeApiError(result.error) : null;
  const busy = result.isLoading || access.isFetching;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file || !access.isAdmin || busy || submitting.current) return;
    submitting.current = true;
    try {
      // RTK owns the pending/result/error state. A failure never triggers replay.
      await importBlueprint({ provisioningUpload: { file } });
    } finally {
      submitting.current = false;
    }
  };

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.provisioning.title")} />
      {access.isLoading ? (
        <p role="status">{t("common.loading")}</p>
      ) : access.isError ? (
        <div role="alert">
          <p>{t("rework.provisioning.authorityUnavailable")}</p>
          <Button type="button" color="primary" variant="outlined" size="medium" onClick={() => void access.refetch()}>
            {t("rework.provisioning.retryAuthority")}
          </Button>
        </div>
      ) : !access.isAdmin ? (
        <p role="alert">{t("rework.provisioning.forbidden")}</p>
      ) : (
        <>
          <p>{t("rework.provisioning.description")}</p>
          <form onSubmit={submit} aria-busy={result.isLoading}>
            <fieldset disabled={busy} className={styles.fields}>
              <legend>{t("rework.provisioning.bundle")}</legend>
              <FileDropzone
                accept=".zip,application/zip,application/x-zip-compressed"
                hint={file ? file.name : t("rework.provisioning.choose")}
                subHint={t("rework.provisioning.format")}
                onFile={(next) => {
                  if (busy || submitting.current) return;
                  setFile(next);
                  result.reset();
                }}
              />
              <Button type="submit" color="primary" variant="filled" size="medium" disabled={!file || busy}>
                {t(result.isLoading ? "rework.provisioning.importing" : "rework.provisioning.import")}
              </Button>
            </fieldset>
          </form>
          {result.isLoading && <p role="status">{t("rework.provisioning.pending")}</p>}
          {error && (
            <div role="alert" className={styles.error}>
              <p>{t("rework.provisioning.failed")}</p>
              <p>
                {error.detail === "not_yet_supported"
                  ? t("rework.provisioning.unsupported")
                  : error.status
                    ? error.detail
                    : t("rework.provisioning.networkError")}
              </p>
              <p>{t("rework.provisioning.replay")}</p>
            </div>
          )}
          {result.isSuccess && result.data && (
            <section role="status" className={styles.report}>
              <h2>{t("rework.provisioning.completed")}</h2>
              <dl className={styles.counts}>
                {(
                  ["identities_resolved", "identities_created", "spaces_reconciled", "grants_acknowledged"] as const
                ).map((key) => (
                  <div key={key}>
                    <dt>{t(`rework.provisioning.counts.${key}`)}</dt>
                    <dd>{result.data[key]}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
          <p className={styles.note}>{t("rework.provisioning.additive")}</p>
        </>
      )}
    </div>
  );
}
