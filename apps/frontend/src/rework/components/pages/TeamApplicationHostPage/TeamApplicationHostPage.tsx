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

import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import { lazy, Suspense, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import type { ApplicationSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam.ts";
import {
  ApplicationErrorBoundary,
  type ApplicationBoundaryFailure,
} from "@rework/features/applications/ApplicationErrorBoundary.tsx";
import type { FredApplicationRegistration } from "@rework/features/applications/applicationHost.ts";
import { applicationRegistry } from "@rework/features/applications/generated/applicationRegistry.ts";
import { applicationRouteBasePath, applicationRouteTarget } from "@rework/features/applications/applicationPath.ts";
import { createApplicationRequest } from "@rework/features/applications/applicationRequest.ts";
import {
  loadApplicationModule,
  resolveApplicationRegistration,
  type ApplicationResolution,
} from "@rework/features/applications/applicationResolution.ts";
import { useTeamApplications } from "@rework/features/applications/useTeamApplications.ts";
import styles from "./TeamApplicationHostPage.module.css";

type HostState =
  | "catalog-loading"
  | "unavailable"
  | "missing-module"
  | "registration-id-mismatch"
  | "unsupported-host-version"
  | "version-mismatch"
  | "contract-mismatch"
  | "module-load"
  | "render";

function ApplicationHostState({ state }: { state: HostState }) {
  const { t } = useTranslation();
  const loading = state === "catalog-loading";
  return (
    <div className={styles.state} role={loading ? "status" : "alert"}>
      <PageEmptyState
        icon={loading ? "sync" : "widgets"}
        message={t(`teamAppsPage.host.${state}`, { defaultValue: t("teamAppsPage.host.unavailable") })}
      />
    </div>
  );
}

interface AuthorizedApplicationProps {
  application: ApplicationSummary;
  registration: FredApplicationRegistration;
  teamId: string;
  teamName: string;
  subPath: string;
}

type ApplicationResolutionStatus = ApplicationResolution["status"];
const CATALOG_REVISION_PATTERN = /^sha256:[0-9a-f]{64}$/;
const INVALID_CATALOG_REVISION_DIAGNOSTIC = "<invalid>";

function useApplicationResolutionDiagnostic(
  applicationId: string,
  status: ApplicationResolutionStatus,
  catalogRevision: string,
) {
  const diagnosticRevision = CATALOG_REVISION_PATTERN.test(catalogRevision)
    ? catalogRevision
    : INVALID_CATALOG_REVISION_DIAGNOSTIC;
  const previousResolution = useRef<{
    applicationId: string;
    status: ApplicationResolutionStatus;
    diagnosticRevision: string;
  } | null>(null);

  useEffect(() => {
    if (
      previousResolution.current?.applicationId === applicationId &&
      previousResolution.current.status === status &&
      previousResolution.current.diagnosticRevision === diagnosticRevision
    ) {
      return;
    }

    previousResolution.current = { applicationId, status, diagnosticRevision };
    if (status !== "ready") {
      // Do not include catalog or registry payloads: the stable failure class
      // and authorized application id are sufficient when revision validation
      // fails. Only a canonical SHA-256 revision may enter the diagnostic.
      console.error(
        `[applications] ${status} resolution failure for ${applicationId} at catalog revision ${diagnosticRevision}`,
      );
    }
  }, [applicationId, diagnosticRevision, status]);
}

function AuthorizedApplication({ application, registration, teamId, teamName, subPath }: AuthorizedApplicationProps) {
  const { i18n } = useTranslation();
  const navigate = useNavigate();
  const ApplicationPage = useMemo(() => lazy(() => loadApplicationModule(registration)), [registration]);
  const request = useMemo(() => createApplicationRequest(application.id, teamId), [application.id, teamId]);
  const basePath = applicationRouteBasePath(teamId, application.id);
  const context = useMemo(
    () => ({
      team: { id: teamId, name: teamName, isPersonal: false as const },
      route: {
        basePath,
        subPath,
        navigate: (relativePath: string, options?: { replace?: boolean }) =>
          navigate(applicationRouteTarget(basePath, relativePath), options),
      },
      locale: i18n.resolvedLanguage ?? i18n.language ?? "en",
      request,
    }),
    [basePath, i18n.language, i18n.resolvedLanguage, navigate, request, subPath, teamId, teamName],
  );
  const failureFallback = (failure: ApplicationBoundaryFailure) => <ApplicationHostState state={failure} />;

  return (
    <ApplicationErrorBoundary applicationId={application.id} fallback={failureFallback}>
      <Suspense fallback={<ApplicationHostState state="catalog-loading" />}>
        <ApplicationPage application={application} context={context} />
      </Suspense>
    </ApplicationErrorBoundary>
  );
}

interface ResolvedApplicationProps {
  application: ApplicationSummary;
  catalogRevision: string;
  teamId: string;
  teamName: string;
  subPath: string;
}

function ResolvedApplication({ application, catalogRevision, teamId, teamName, subPath }: ResolvedApplicationProps) {
  const resolution = resolveApplicationRegistration(application, applicationRegistry);
  useApplicationResolutionDiagnostic(application.id, resolution.status, catalogRevision);

  if (resolution.status !== "ready") return <ApplicationHostState state={resolution.status} />;

  return (
    <AuthorizedApplication
      key={`${teamId}:${application.id}:${application.version}:${application.contract_digest}`}
      application={application}
      registration={resolution.registration}
      teamId={teamId}
      teamName={teamName}
      subPath={subPath}
    />
  );
}

export default function TeamApplicationHostPage() {
  const { teamId, appId, "*": subPath = "" } = useParams<{ teamId: string; appId: string; "*": string }>();
  const { isPersonalTeam, selectedTeam } = useSelectedTeam();
  const { data, isLoading, isError } = useTeamApplications(teamId, isPersonalTeam || !appId);

  if (isLoading) return <ApplicationHostState state="catalog-loading" />;
  if (!teamId || !appId || isPersonalTeam || isError || !data) return <ApplicationHostState state="unavailable" />;

  // Searching the authorized response before touching the static registry is
  // the important ordering: an unknown or unentitled id cannot probe whether
  // this Fred build happens to contain a module with that name.
  const application = data.items?.find((candidate) => candidate.id === appId);
  if (!application) return <ApplicationHostState state="unavailable" />;

  return (
    <ResolvedApplication
      application={application}
      catalogRevision={data.catalog_revision}
      teamId={teamId}
      teamName={selectedTeam?.name ?? teamId}
      subPath={subPath}
    />
  );
}
