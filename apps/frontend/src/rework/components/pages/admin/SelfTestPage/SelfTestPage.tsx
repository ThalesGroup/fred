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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { usePipelineRun } from "../../../../features/pipeline/usePipelineRun";
import { selfTestScenario } from "../../../../features/pipeline/scenarios/selfTestScenario";
import {
  credentialExpiryScenario,
  expiryWaitSeconds,
} from "../../../../features/pipeline/scenarios/credentialExpiryScenario";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { MAX_HOLD_MINUTES } from "../../../../features/pipeline/types";
import { useAuthzProbeRun } from "../../../../features/pipeline/useAuthzProbeRun";
import { useListUsersQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { StepReportPanel } from "./StepReportPanel";
import styles from "./SelfTestPage.module.css";

interface SectionProps {
  /** Avoid overlapping diagnostics in the same page. */
  busy: boolean;
  onRunningChange: (running: boolean) => void;
}

function FunctionalSelfTestSection({ busy, onRunningChange }: SectionProps) {
  const { t } = useTranslation();
  const { steps, isRunning, start } = usePipelineRun(selfTestScenario);

  useEffect(() => onRunningChange(isRunning), [isRunning, onRunningChange]);

  return (
    <section className={styles.testSection}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t("rework.selftest.functional.title")}</h2>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          icon={{ category: "outlined", type: "check_circle", filled: false }}
          onClick={start}
          disabled={busy}
        >
          {isRunning ? t("rework.selftest.report.running") : t("rework.selftest.functional.run")}
        </Button>
      </div>
      <p className={styles.subtitle}>{t("rework.selftest.functional.subtitle")}</p>
      <StepReportPanel steps={steps} isRunning={isRunning} emptyLabel={t("rework.selftest.report.empty")} />
    </section>
  );
}

function AuthzSelfTestSection({ busy, onRunningChange }: SectionProps) {
  const { t } = useTranslation();
  const { steps, isRunning, runForMyself, runForProfile } = useAuthzProbeRun();
  const { data: users } = useListUsersQuery();
  const [username, setUsername] = useState<string | undefined>(undefined);
  const [password, setPassword] = useState("");
  const realmConfig = useMemo(() => KeyCloakService.GetKeycloakRealmConfig(), []);
  const expiryScenario = useMemo(() => credentialExpiryScenario(), []);
  const expiryRun = usePipelineRun(expiryScenario);
  // The wait is quoted from the session as it was when the notice opened, so
  // the figure the admin accepts is the one the run then uses.
  const [pendingExpiry, setPendingExpiry] = useState<{ waitSeconds: number | null } | null>(null);

  useEffect(() => onRunningChange(isRunning || expiryRun.isRunning), [isRunning, expiryRun.isRunning, onRunningChange]);

  const userOptions: OptionModel<string>[] = useMemo(
    () =>
      (users ?? [])
        .filter((u) => u.username)
        .map((u) => ({ key: u.id, value: u.username as string, label: u.username as string })),
    [users],
  );

  const handleRunForProfile = () => {
    if (!username || !password) return;
    runForProfile(username, password);
    setPassword("");
  };

  return (
    <section className={styles.testSection}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t("rework.selftest.authz.title")}</h2>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          icon={{ category: "outlined", type: "admin_panel_settings", filled: false }}
          onClick={runForMyself}
          disabled={busy}
        >
          {isRunning ? t("rework.selftest.report.running") : t("rework.selftest.authz.runSelf")}
        </Button>
      </div>
      <p className={styles.subtitle}>{t("rework.selftest.authz.subtitle")}</p>

      <div className={styles.testProfilePanel}>
        <h3 className={styles.testProfileTitle}>{t("rework.selftest.authz.testProfile.title")}</h3>
        {realmConfig ? (
          <>
            <div className={styles.testProfileFields}>
              <Select
                size="medium"
                options={userOptions}
                value={username}
                onChange={setUsername}
                label={t("rework.selftest.authz.testProfile.usernameLabel")}
                placeholder={t("rework.selftest.authz.testProfile.usernamePlaceholder")}
              />
              <TextInput
                type="password"
                label={t("rework.selftest.authz.testProfile.passwordLabel")}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <Button
                color="secondary"
                variant="outlined"
                size="medium"
                onClick={handleRunForProfile}
                disabled={busy || !username || !password}
              >
                {t("rework.selftest.authz.testProfile.run")}
              </Button>
            </div>
            <p className={styles.testProfileCaption}>{t("rework.selftest.authz.testProfile.caption")}</p>
          </>
        ) : (
          <p className={styles.testProfileCaption}>{t("rework.selftest.authz.testProfile.disabledInsecure")}</p>
        )}
      </div>

      <StepReportPanel steps={steps} isRunning={isRunning} emptyLabel={t("rework.selftest.report.empty")} />

      {realmConfig && (
        <section className={styles.testSection}>
          <div className={styles.header}>
            <h3 className={styles.testProfileTitle}>{t("rework.selftest.authz.expiry.title")}</h3>
            <Button
              color="secondary"
              variant="outlined"
              size="medium"
              icon={{ category: "outlined", type: "schedule", filled: false }}
              onClick={() =>
                setPendingExpiry({ waitSeconds: expiryWaitSeconds(KeyCloakService.GetTokenSecondsLeft()) })
              }
              disabled={busy}
            >
              {t("rework.selftest.authz.expiry.run")}
            </Button>
          </div>
          <p className={styles.testProfileCaption}>
            {t("rework.selftest.authz.expiry.caption", { maxMinutes: MAX_HOLD_MINUTES })}
          </p>
          <ConfirmationDialog
            open={pendingExpiry !== null}
            title={t("rework.selftest.authz.expiry.warning.title")}
            message={
              pendingExpiry?.waitSeconds
                ? t("rework.selftest.authz.expiry.warning.message", {
                    minutes: Math.max(1, Math.round(pendingExpiry.waitSeconds / 60)),
                  })
                : t("rework.selftest.authz.expiry.warning.messageUnknownWait")
            }
            confirmLabel={t("rework.selftest.authz.expiry.warning.confirm")}
            cancelLabel={t("common.cancel")}
            onConfirm={() => {
              setPendingExpiry(null);
              expiryRun.start();
            }}
            onCancel={() => setPendingExpiry(null)}
          />
          <StepReportPanel
            steps={expiryRun.steps}
            isRunning={expiryRun.isRunning}
            emptyLabel={t("rework.selftest.report.empty")}
          />
        </section>
      )}
    </section>
  );
}

export default function SelfTestPage() {
  const { t } = useTranslation();
  const [functionalRunning, setFunctionalRunning] = useState(false);
  const [authzRunning, setAuthzRunning] = useState(false);
  const busy = functionalRunning || authzRunning;

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.selftest.page.title")} />
      <FunctionalSelfTestSection busy={busy} onRunningChange={setFunctionalRunning} />
      <AuthzSelfTestSection busy={busy} onRunningChange={setAuthzRunning} />
    </div>
  );
}
