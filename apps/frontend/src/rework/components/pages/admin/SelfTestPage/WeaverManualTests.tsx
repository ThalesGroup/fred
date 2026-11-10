// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Select from "@shared/molecules/Select/Select";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import { useSpaceMembersQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Role } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { loginWithPassword } from "../../../../features/pipeline/keycloakDirectGrant";
import { useRunner, useScenarioRun } from "../../../../features/pipeline/useScenarioRun";
import { runStep } from "../../../../features/pipeline/step";
import { expiry } from "../../../../features/pipeline/weaver/runtime";
import type { WeaverChecks } from "../../../../features/pipeline/weaver/checks";
import { checkPersonalIsolation } from "../../../../features/pipeline/weaver/authorization";
import {
  hasCampaignContentRole,
  recoverCampaign,
  runCampaign,
  type CampaignJournal,
} from "../../../../features/pipeline/weaver/campaign";
import { managerActor } from "../../../../features/imports/managerImportRun";
import { StepReportPanel } from "./StepReportPanel";
import type { ReportSection } from "./report";
import styles from "./SelfTestPage.module.css";

interface Props {
  context: WeaverChecks;
  campaignContext?: WeaverChecks & { roles: Role[] };
  campaignScopeName?: string;
  expiryScopeName?: string;
  busy: boolean;
  onRunningChange: (running: boolean) => void;
  onReportsChange: (reports: ReportSection[]) => void;
}
export function WeaverManualTests({
  context,
  campaignContext,
  campaignScopeName,
  expiryScopeName,
  busy,
  onRunningChange,
  onReportsChange,
}: Props) {
  const { t } = useTranslation();
  const campaign = useRunner();
  const expiryRun = useScenarioRun(expiry, context);
  const keycloak = KeyCloakService.GetIdentityProvider() === "keycloak";
  const [account, setAccount] = useState<string>();
  const [password, setPassword] = useState("");
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [pending, setPending] = useState<"campaign" | "expiry" | null>(null);
  const [campaignAt, setCampaignAt] = useState<Date>();
  const [expiryAt, setExpiryAt] = useState<Date>();
  const [actor] = useState(managerActor);
  const journalKey = `selftest-weaver-role-campaign:${actor}`;
  const [recovery, setRecovery] = useState(() => {
    try {
      return localStorage.getItem(journalKey) !== null;
    } catch {
      return true;
    }
  });
  const [recovering, setRecovering] = useState(false);
  const campaignTeamId = campaignContext?.spaceKind === "team" ? campaignContext.spaceId : "";
  const campaignBusy = busy || campaign.isRunning;
  const campaignEligible =
    !!campaignTeamId && !!campaignContext?.roles.includes("owner") && hasCampaignContentRole(campaignContext.roles);
  const showAccounts = keycloak && campaignEligible && !recovery;
  const roster = useSpaceMembersQuery(
    { id: campaignTeamId, after: cursors[cursors.length - 1] },
    { skip: !showAccounts, refetchOnMountOrArgChange: true },
  );
  const memberPage = showAccounts && !roster.isFetching && !roster.isError ? roster.currentData : undefined;
  const accounts = (memberPage?.items ?? []).flatMap(({ user, roles }) =>
    user.id !== context.userId && user.username && hasCampaignContentRole(roles)
      ? [{ key: user.id, value: user.id, label: user.username }]
      : [],
  );
  const username = accounts.find((option) => option.value === account)?.label;
  const campaignReady = !campaignBusy && showAccounts && !!username && !!password;
  const expiryEligible = !!context.spaceId && ["team", "project", "personal"].includes(context.spaceKind ?? "");
  const campaignScope = t("rework.selftest.weaver.manual.campaignTarget", { name: campaignScopeName ?? "" });
  const expiryScope = t("rework.selftest.weaver.manual.expiryTarget", { name: expiryScopeName ?? "" });
  const campaignBaseTitle = t("rework.selftest.authz.campaign.title");
  const campaignTitle = recovering
    ? `${campaignBaseTitle} - ${t("rework.selftest.weaver.manual.savedTarget")}`
    : campaignTeamId
      ? `${campaignBaseTitle} - ${campaignScope}`
      : campaignBaseTitle;
  const expiryBaseTitle = t("rework.selftest.authz.expiry.title");
  const expiryTitle = expiryEligible ? `${expiryBaseTitle} - ${expiryScope}` : expiryBaseTitle;
  useEffect(
    () => onRunningChange(campaign.isRunning || expiryRun.isRunning),
    [campaign.isRunning, expiryRun.isRunning, onRunningChange],
  );
  useEffect(
    () =>
      onReportsChange([
        { title: campaignTitle, steps: campaign.steps, startedAt: campaignAt },
        { title: expiryTitle, steps: expiryRun.steps, startedAt: expiryAt },
      ]),
    [campaignTitle, expiryTitle, campaign.steps, expiryRun.steps, campaignAt, expiryAt, onReportsChange],
  );
  const clearCredentials = useCallback(() => {
    setAccount(undefined);
    setPassword("");
  }, []);
  useEffect(() => {
    clearCredentials();
    setCursors([undefined]);
    setPending(null);
  }, [campaignTeamId, clearCredentials, context.userId, keycloak]);
  const startCampaign = (recover = false) => {
    if (campaignBusy || (!recover && !campaignReady)) return;
    setRecovering(recover);
    setCampaignAt(new Date());
    let profile = !recover && username && account ? { account, username, password } : undefined;
    clearCredentials();
    void campaign.run(async (report, signal) => {
      const checkOperator = () => {
        signal.throwIfAborted();
        if (managerActor() !== actor) throw new Error("The operator identity changed");
      };
      await runStep(report, "campaign-lock", "Run one isolated campaign in this browser", async () => {
        if (!navigator.locks) throw new Error("Web Locks support is required for safe recovery");
        await navigator.locks.request(journalKey, { ifAvailable: true }, async (lock) => {
          if (!lock) throw new Error("Another campaign is running in this browser");
          checkOperator();
          const storage = {
            read: () => {
              const saved = localStorage.getItem(journalKey);
              return saved ? (JSON.parse(saved) as CampaignJournal) : null;
            },
            save: (value: CampaignJournal | null) => {
              if (value) localStorage.setItem(journalKey, JSON.stringify(value));
              else localStorage.removeItem(journalKey);
              setRecovery(value !== null);
            },
          };
          try {
            if (recover) await recoverCampaign(context, storage, report);
            else if (campaignContext && profile) {
              if (localStorage.getItem(journalKey) !== null) throw new Error("Recover the interrupted campaign first");
              const { account, username, password } = profile;
              profile = undefined;
              const testToken = await runStep(
                report,
                "campaign-login",
                "Sign in as the dedicated test account",
                async () => {
                  let realm = null;
                  try {
                    realm = KeyCloakService.GetKeycloakRealmConfig();
                  } catch {
                    // Keep provider configuration out of the report.
                  }
                  if (!realm) throw new Error("Test account sign-in is unavailable");
                  return { value: await loginWithPassword(realm, username, password, signal) };
                },
              );
              checkOperator();
              if (testToken) {
                const { identitiesVerified } = await checkPersonalIsolation(
                  context.userId,
                  account,
                  testToken,
                  report,
                  signal,
                );
                checkOperator();
                if (identitiesVerified) await runCampaign(campaignContext, testToken, storage, report, signal);
              }
            }
          } finally {
            setRecovery(localStorage.getItem(journalKey) !== null);
          }
        });
        return { value: true };
      });
    });
  };
  return (
    <>
      <div className={styles.testProfilePanel}>
        <h3 className={styles.testProfileTitle}>{campaignTitle}</h3>
        {!campaignTeamId && <p>{t("rework.selftest.weaver.manual.campaignMissingScope")}</p>}
        {campaignTeamId && !campaignEligible && <p>{t("rework.selftest.weaver.manual.campaignMissingRole")}</p>}
        {showAccounts && (
          <>
            <div className={styles.testProfileFields}>
              <Select
                size="medium"
                label={t("rework.selftest.weaver.manual.usernameLabel")}
                placeholder={t("rework.selftest.authz.testProfile.usernamePlaceholder")}
                options={accounts}
                disabled={campaignBusy || !accounts.length}
                value={username ? account : undefined}
                onChange={(value) => {
                  setAccount(value);
                  setPassword("");
                }}
              />
              <TextInput
                type="password"
                label={t("rework.selftest.authz.testProfile.passwordLabel")}
                disabled={campaignBusy || !username}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            {roster.isError ? (
              <div className={styles.testProfileFields}>
                <p role="alert" className={styles.testProfileCaption}>
                  {t("rework.selftest.weaver.manual.accountsUnavailable")}
                </p>
                <Button
                  color="secondary"
                  variant="outlined"
                  size="small"
                  disabled={campaignBusy}
                  onClick={() => {
                    clearCredentials();
                    void roster.refetch();
                  }}
                >
                  {t("rework.spaceMembers.refresh")}
                </Button>
              </div>
            ) : !memberPage ? (
              <p role="status" className={styles.testProfileCaption}>
                {t("common.loading")}
              </p>
            ) : !accounts.length ? (
              <p className={styles.testProfileCaption}>{t("rework.selftest.weaver.manual.accountsEmpty")}</p>
            ) : null}
            {(cursors.length > 1 || memberPage?.next_cursor) && (
              <div className={styles.testProfileFields}>
                <Button
                  color="secondary"
                  variant="outlined"
                  size="small"
                  disabled={campaignBusy || cursors.length < 2}
                  onClick={() => {
                    clearCredentials();
                    setCursors((pages) => pages.slice(0, -1));
                  }}
                >
                  {t("dataTable.pagination.prev")}
                </Button>
                <Button
                  color="secondary"
                  variant="outlined"
                  size="small"
                  disabled={campaignBusy || !memberPage?.next_cursor}
                  onClick={() => {
                    const next = memberPage?.next_cursor;
                    if (!next) return;
                    clearCredentials();
                    setCursors((pages) => [...pages, next]);
                  }}
                >
                  {t("dataTable.pagination.next")}
                </Button>
              </div>
            )}
            <p className={styles.testProfileCaption}>{t("rework.selftest.weaver.manual.keycloakCaption")}</p>
          </>
        )}
        {!keycloak && <p>{t("rework.selftest.weaver.manual.authRequired")}</p>}
        <p className={styles.testProfileCaption}>{t("rework.selftest.weaver.manual.caption")}</p>
        <Button
          color="secondary"
          variant="outlined"
          size="medium"
          disabled={!campaignReady}
          onClick={() => setPending("campaign")}
        >
          {t("rework.selftest.authz.campaign.run")}
        </Button>
        {recovery && (
          <>
            <p role="alert">{t("rework.selftest.weaver.manual.recovery")}</p>
            <Button
              color="secondary"
              variant="outlined"
              size="medium"
              disabled={campaignBusy}
              onClick={() => startCampaign(true)}
            >
              {t("rework.selftest.weaver.manual.recover")}
            </Button>
          </>
        )}
        {campaignAt && <p>{t("rework.selftest.weaver.started", { time: campaignAt.toLocaleString() })}</p>}
        <StepReportPanel
          reportTitle={campaignTitle}
          steps={campaign.steps}
          isRunning={campaign.isRunning}
          durationMs={campaign.durationMs}
          emptyLabel={t("rework.selftest.report.empty")}
        />
      </div>
      <div className={styles.testProfilePanel}>
        <h3 className={styles.testProfileTitle}>{expiryTitle}</h3>
        {!expiryEligible && <p>{t("rework.selftest.weaver.manual.expiryMissingScope")}</p>}
        <p className={styles.testProfileCaption}>{t("rework.selftest.weaver.manual.expiryCaption")}</p>
        <Button
          color="secondary"
          variant="outlined"
          size="medium"
          disabled={busy || !expiryEligible}
          onClick={() => setPending("expiry")}
        >
          {t("rework.selftest.authz.expiry.run")}
        </Button>
        {expiryAt && <p>{t("rework.selftest.weaver.started", { time: expiryAt.toLocaleString() })}</p>}
        <StepReportPanel
          reportTitle={expiryTitle}
          steps={expiryRun.steps}
          isRunning={expiryRun.isRunning}
          durationMs={expiryRun.durationMs}
          emptyLabel={t("rework.selftest.report.empty")}
        />
      </div>
      <ConfirmationDialog
        open={pending !== null}
        title={pending === "campaign" ? campaignTitle : expiryTitle}
        message={t(`rework.selftest.weaver.manual.${pending === "campaign" ? "confirmation" : "expiryConfirmation"}`, {
          name: pending === "campaign" ? campaignScopeName : expiryScopeName,
        })}
        confirmLabel={t(
          pending === "campaign"
            ? "rework.selftest.authz.campaign.confirm"
            : "rework.selftest.authz.expiry.warning.confirm",
        )}
        cancelLabel={t("common.cancel")}
        confirmDisabled={pending === "campaign" && !campaignReady}
        onCancel={() => setPending(null)}
        onConfirm={() => {
          const action = pending;
          setPending(null);
          if (action === "campaign") startCampaign();
          else if (action === "expiry" && expiryEligible) {
            setExpiryAt(new Date());
            void expiryRun.start();
          }
        }}
      />
    </>
  );
}
