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

import { createContext } from "react";

export const ApplicationContext = createContext({ darkMode: false });

export function useTranslation() {
  return {
    t: (key: string) => key,
    i18n: { language: "en", resolvedLanguage: "en" },
  };
}

export function useParams() {
  return { teamId: "team-1", appId: "example", "*": "" };
}

export function useNavigate() {
  return () => undefined;
}

export function useSelectedTeam() {
  return {
    isPersonalTeam: false,
    selectedTeam: { id: "team-1", name: "Team One" },
  };
}

export function useTeamApplications() {
  const childOrigin = new URLSearchParams(window.location.search).get(
    "childOrigin",
  );
  if (!childOrigin) throw new Error("childOrigin is required");
  const childUrl = new URL("/application-download-child.html", childOrigin);
  childUrl.searchParams.set("hostOrigin", window.location.origin);
  return {
    data: {
      items: [
        {
          id: "example",
          version: "1.0.0",
          name: { en: "Example App" },
          description: { en: "Download fixture" },
          icon: "extension",
          ui_prefix: childUrl.href,
        },
      ],
    },
    isLoading: false,
    isError: false,
  };
}

export function useLazyGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery() {
  return [() => ({ unwrap: async () => [] })];
}

export function useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery() {
  return [() => ({ unwrap: async () => [] })];
}

export function createApplicationRequest() {
  return async () =>
    new Response("Unexpected application request", { status: 500 });
}

export default function PageEmptyState({ message }: { message: string }) {
  return <span>{message}</span>;
}
