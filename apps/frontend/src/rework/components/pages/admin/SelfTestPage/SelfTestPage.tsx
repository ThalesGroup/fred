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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { usePipelineRun } from "../../../../features/pipeline/usePipelineRun";
import { selfTestScenario } from "../../../../features/pipeline/scenarios/selfTestScenario";
import { useAuthzProbeRun } from "../../../../features/pipeline/useAuthzProbeRun";
import { useListUsersQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import { StepReportPanel } from "./StepReportPanel";
import styles from "./SelfTestPage.module.css";

function FunctionalSelfTestSection() {
  const { t } = useTranslation();
  const { steps, isRunning, start } = usePipelineRun(selfTestScenario);

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
          disabled={isRunning}
        >
          {isRunning ? t("rework.selftest.report.running") : t("rework.selftest.functional.run")}
        </Button>
      </div>
      <p className={styles.subtitle}>{t("rework.selftest.functional.subtitle")}</p>
      <StepReportPanel steps={steps} isRunning={isRunning} emptyLabel={t("rework.selftest.report.empty")} />
    </section>
  );
}

function AuthzSelfTestSection() {
  const { t } = useTranslation();
  const { steps, isRunning, runForMyself, runForProfile } = useAuthzProbeRun();
  const { data: users } = useListUsersQuery();
  const [username, setUsername] = useState<string | undefined>(undefined);
  const [password, setPassword] = useState("");

  const realmConfig = useMemo(() => KeyCloakService.GetKeycloakRealmConfig(), []);

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
          disabled={isRunning}
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
                onChange={(e) => setPassword(e.target.value)}
              />
              <Button
                color="secondary"
                variant="outlined"
                size="medium"
                onClick={handleRunForProfile}
                disabled={isRunning || !username || !password}
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
    </section>
  );
}

export default function SelfTestPage() {
  const { t } = useTranslation();

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>{t("rework.selftest.page.title")}</h1>
      <FunctionalSelfTestSection />
      <AuthzSelfTestSection />
    </div>
  );
}
