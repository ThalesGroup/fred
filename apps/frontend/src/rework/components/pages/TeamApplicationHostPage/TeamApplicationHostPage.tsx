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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import type { ApplicationSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import {
  useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useLazyGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery,
} from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam.ts";
import { ApplicationErrorBoundary } from "@rework/features/applications/ApplicationErrorBoundary.tsx";
import {
  ACCEPTED_APP_PROTOCOL_VERSIONS,
  applicationFrameTarget,
  FRED_APP_PROTOCOL_VERSION,
  parseApplicationFrameMessage,
  type ApplicationHostMessage,
} from "@rework/features/applications/applicationHost.ts";
import { applicationLocaleText } from "@rework/features/applications/applicationI18n.ts";
import {
  applicationChatRouteTarget,
  applicationChatSessionTarget,
  applicationNewChatTarget,
  applicationRouteBasePath,
  applicationRouteTarget,
} from "@rework/features/applications/applicationPath.ts";
import { createApplicationRequest } from "@rework/features/applications/applicationRequest.ts";
import { useTeamApplications } from "@rework/features/applications/useTeamApplications.ts";
import styles from "./TeamApplicationHostPage.module.css";

type HostState = "catalog-loading" | "unavailable" | "connecting" | "protocol-mismatch" | "unreachable" | "render";

/** A frame that never announces itself is indistinguishable from a broken one. */
export const APPLICATION_HANDSHAKE_TIMEOUT_MS = 15_000;

/** Bound on concurrent proxied calls, so one frame cannot exhaust the tab. */
export const MAX_IN_FLIGHT_APPLICATION_REQUESTS = 16;

function ApplicationHostState({ state }: { state: HostState }) {
  const { t } = useTranslation();
  const loading = state === "catalog-loading" || state === "connecting";
  return (
    <div className={styles.state} role={loading ? "status" : "alert"}>
      <PageEmptyState
        icon={loading ? "sync" : "widgets"}
        message={t(`teamAppsPage.host.${state}`, { defaultValue: t("teamAppsPage.host.unavailable") })}
      />
    </div>
  );
}

type FrameStatus = "connecting" | "ready" | "protocol-mismatch" | "unreachable";

interface ApplicationFrameProps {
  application: ApplicationSummary;
  src: string;
  targetOrigin: string;
  teamId: string;
  teamName: string;
  subPath: string;
}

function pathnameOf(path: string): string {
  const queryIndex = path.indexOf("?");
  return queryIndex === -1 ? path : path.slice(0, queryIndex);
}

/**
 * Host one application in an iframe. The frame is a separate document, so the
 * whole contract runs over postMessage — no DOM reach-in, no shared globals,
 * and the target origin comes from the configured URL. That is deliberate: the
 * same code works unchanged once applications move to their own origin.
 *
 * Same-origin this is NOT an isolation boundary. The frame can reach Fred's
 * origin directly; the discipline here buys a stable contract, not containment.
 */
function ApplicationFrame({ application, src, targetOrigin, teamId, teamName, subPath }: ApplicationFrameProps) {
  const { i18n } = useTranslation();
  const navigate = useNavigate();
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [status, setStatus] = useState<FrameStatus>("connecting");

  const locale = i18n.resolvedLanguage ?? i18n.language ?? "en";
  const basePath = applicationRouteBasePath(teamId, application.id);
  const request = useMemo(() => createApplicationRequest(application.id, teamId), [application.id, teamId]);

  // openChat navigates after awaiting two lookups. Without this the user can
  // click away, the listing lands, and the router yanks them back — useNavigate
  // stays live after unmount, so the await is the hazard, not the click.
  const goneRef = useRef(false);
  useEffect(() => {
    goneRef.current = false;
    return () => {
      goneRef.current = true;
    };
  }, []);

  const [fetchTeamSessions] = useLazyGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery();
  const [fetchTeamAgents] = useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery();

  /**
   * Resolve where "open a conversation" should land.
   *
   * A frame-supplied session id is treated as a candidate and nothing more: it
   * is matched against the caller's own sessions, and the agent instance comes
   * from the matched record rather than the frame. Anything that does not match
   * falls back to a new conversation, so the failure mode is a fresh chat and
   * never a route the application chose — that covers an unknown id, another
   * user's, a listing that fails, and one that has aged past the listing's
   * newest-50 window.
   */
  const openChat = useCallback(
    async (candidateSessionId: string | null) => {
      if (candidateSessionId) {
        try {
          const sessions = await fetchTeamSessions({ teamId }).unwrap();
          if (goneRef.current) return;
          const match = sessions?.find((s) => s.session_id === candidateSessionId);
          if (match?.agent_instance_id) {
            navigate(applicationChatSessionTarget(teamId, match.agent_instance_id, match.session_id));
            return;
          }
        } catch {
          // Fall through: an unavailable listing must not strand the user.
        }
      }
      // No conversation to resume: start a new one. Which agent is the host's
      // choice, not the frame's — with a single enabled agent that is
      // unambiguous, and otherwise the picker is the honest answer rather than
      // guessing on the user's behalf.
      try {
        const agents = await fetchTeamAgents({ teamId }).unwrap();
        if (goneRef.current) return;
        // Suspended instances are hidden from chat, so they must not be
        // counted here either — otherwise two "agents" could look ambiguous
        // when only one is actually reachable.
        const enabled = (agents ?? []).filter((a) => a.status === "enabled" && !a.suspension_reason);
        if (enabled.length === 1) {
          navigate(applicationNewChatTarget(teamId, enabled[0].agent_instance_id));
          return;
        }
      } catch {
        // Fall through to the picker: never strand the user on a failed lookup.
      }
      if (goneRef.current) return;
      navigate(applicationChatRouteTarget(teamId));
    },
    [fetchTeamAgents, fetchTeamSessions, navigate, teamId],
  );

  // The message listener is installed once per frame but must read the current
  // route and locale, so those travel through a ref instead of resubscribing.
  const contextRef = useRef({ basePath, subPath, locale, teamName });
  const sentSubPathRef = useRef<string | null>(null);

  useEffect(() => {
    contextRef.current = { basePath, subPath, locale, teamName };
  });

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;

    const inFlight = new Map<string, AbortController>();
    let disposed = false;

    const post = (message: ApplicationHostMessage) => {
      frame.contentWindow?.postMessage(message, targetOrigin);
    };

    const proxyRequest = async (requestId: string, path: string, init: RequestInit, signal: AbortSignal) => {
      try {
        const response = await request(path, { ...init, signal });
        const body = await response.text();
        if (disposed) return;
        post({
          type: "fred:response",
          requestId,
          status: response.status,
          headers: Object.fromEntries(response.headers),
          body,
        });
      } catch {
        // A rejection here can carry application or upstream data. The frame
        // learns only that its own call failed, and nothing is logged.
        if (!disposed) post({ type: "fred:response-error", requestId });
      } finally {
        inFlight.delete(requestId);
      }
    };

    const onMessage = (event: MessageEvent) => {
      // Identity is the frame's own window. Same-origin today an origin check
      // alone would admit any other Fred document, so it cannot stand in. A
      // detached frame has no content window, and null must never match null.
      if (!frame.contentWindow || event.source !== frame.contentWindow) return;

      const message = parseApplicationFrameMessage(event.data);
      if (!message) return;

      if (message.type === "fred:ready") {
        if (!ACCEPTED_APP_PROTOCOL_VERSIONS.includes(message.protocolVersion)) {
          setStatus("protocol-mismatch");
          return;
        }
        const {
          basePath: currentBase,
          subPath: currentSubPath,
          locale: currentLocale,
          teamName: name,
        } = contextRef.current;
        post({
          type: "fred:context",
          protocolVersion: FRED_APP_PROTOCOL_VERSION,
          applicationId: application.id,
          context: {
            team: { id: teamId, name, isPersonal: false },
            route: { basePath: currentBase, subPath: currentSubPath },
            locale: currentLocale,
          },
        });
        sentSubPathRef.current = currentSubPath;
        setStatus("ready");
        return;
      }

      if (message.type === "fred:open-chat") {
        // The only navigation that leaves this application's subtree. A frame
        // never names a route: without a session candidate this lands on the
        // team's own agents surface, and with one the host resolves the target
        // from ITS session listing rather than trusting the id. So the worst a
        // compromised application can do is reopen a conversation its own user
        // already owns and can already reach from the sidebar.
        void openChat(message.sessionId);
        return;
      }

      if (message.type === "fred:navigate") {
        try {
          const target = applicationRouteTarget(contextRef.current.basePath, message.path);
          sentSubPathRef.current = pathnameOf(message.path);
          navigate(target, { replace: message.replace });
        } catch {
          // An escaping or malformed path is dropped, never surfaced: the
          // router must not move outside this application's own subtree.
        }
        return;
      }

      // The frame's requestId is the channel's only correlation token, so an id
      // that is already running cannot be admitted: a second call under it would
      // be invisible to the bound, unabortable, and answered twice.
      if (inFlight.has(message.requestId) || inFlight.size >= MAX_IN_FLIGHT_APPLICATION_REQUESTS) {
        post({ type: "fred:response-error", requestId: message.requestId });
        return;
      }
      const controller = new AbortController();
      inFlight.set(message.requestId, controller);
      void proxyRequest(
        message.requestId,
        message.path,
        { method: message.method, headers: message.headers, body: message.body ?? undefined },
        controller.signal,
      );
    };

    window.addEventListener("message", onMessage);
    const timer = window.setTimeout(() => {
      if (!disposed) setStatus((current) => (current === "connecting" ? "unreachable" : current));
    }, APPLICATION_HANDSHAKE_TIMEOUT_MS);

    return () => {
      disposed = true;
      window.clearTimeout(timer);
      window.removeEventListener("message", onMessage);
      for (const controller of inFlight.values()) controller.abort();
      inFlight.clear();
    };
  }, [application.id, navigate, openChat, request, targetOrigin, teamId]);

  // Route changes made in Fred (back/forward, a sidebar link) are pushed down.
  // Echoing back the sub-path the frame itself asked for would ping-pong.
  useEffect(() => {
    if (status !== "ready" || sentSubPathRef.current === subPath) return;
    sentSubPathRef.current = subPath;
    frameRef.current?.contentWindow?.postMessage({ type: "fred:route", subPath }, targetOrigin);
  }, [status, subPath, targetOrigin]);

  const connected = status === "connecting" || status === "ready";
  return (
    <div className={styles.host}>
      {status !== "ready" && <ApplicationHostState state={status === "connecting" ? "connecting" : status} />}
      {connected && (
        <iframe
          ref={frameRef}
          className={status === "ready" ? styles.frame : styles.frameLoading}
          src={src}
          title={applicationLocaleText(application.name, locale)}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        />
      )}
    </div>
  );
}

export default function TeamApplicationHostPage() {
  const { teamId, appId, "*": subPath = "" } = useParams<{ teamId: string; appId: string; "*": string }>();
  const { isPersonalTeam, selectedTeam } = useSelectedTeam();
  const { data, isLoading, isError } = useTeamApplications(teamId, isPersonalTeam || !appId);

  if (isLoading) return <ApplicationHostState state="catalog-loading" />;
  if (!teamId || !appId || isPersonalTeam || isError || !data) return <ApplicationHostState state="unavailable" />;

  // Searching the authorized response first is the important ordering: an
  // unknown or unentitled id learns nothing beyond "unavailable", and no frame
  // is created for an application this team may not use.
  const application = data.items?.find((candidate) => candidate.id === appId);
  if (!application) return <ApplicationHostState state="unavailable" />;

  const target = applicationFrameTarget(application, window.location.origin);
  if (!target) return <ApplicationHostState state="unavailable" />;

  return (
    <ApplicationErrorBoundary applicationId={application.id} fallback={<ApplicationHostState state="render" />}>
      <ApplicationFrame
        key={`${teamId}:${application.id}:${target.src}`}
        application={application}
        src={target.src}
        targetOrigin={target.targetOrigin}
        teamId={teamId}
        teamName={selectedTeam?.name ?? teamId}
        subPath={subPath}
      />
    </ApplicationErrorBoundary>
  );
}
