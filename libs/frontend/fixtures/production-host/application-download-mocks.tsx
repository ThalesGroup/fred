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

export function useMySpacesQuery() {
  return {
    currentData: [{ id: "team-1", name: "Team One", kind: "team" }],
  };
}

export function useFrontendProperties() {
  return { siteDisplayName: "Fred" };
}

export function useTeamApplications() {
  const childOrigin = new URLSearchParams(window.location.search).get(
    "childOrigin",
  );
  if (!childOrigin) throw new Error("childOrigin is required");
  const childUrl = new URL("/application-download-child.html", childOrigin);
  childUrl.searchParams.set("hostOrigin", window.location.origin);
  return {
    data: [
      {
        id: "example",
        logical_name: "example",
        source_id: "source-1",
        capability_id: "example",
        entry_permission: "read",
        version: "1.0.0",
        display_name: "Example App",
        description: "Download fixture",
        icon: "extension",
        ui_path: childUrl.href,
      },
    ],
    isLoading: false,
    isError: false,
  };
}

export function useLazyListSessionsQuery() {
  return [() => ({ unwrap: async () => [] })];
}

export function useLazyListAgentInstancesQuery() {
  return [() => ({ unwrap: async () => ({ items: [], next_cursor: null }) })];
}

// The "echo" service records what it received and answers with the bytes reversed.
export function createApplicationRequest() {
  return async (path: string, init: RequestInit = {}) => {
    if (path !== "echo" || !(init.body instanceof Blob))
      return new Response("Unexpected application request", { status: 500 });
    const received = new Uint8Array(await init.body.arrayBuffer());
    (window as unknown as { fixtureUpload: unknown }).fixtureUpload = {
      bytes: Array.from(received),
      type: init.body.type,
    };
    return new Response(received.slice().reverse(), {
      headers: { "content-type": "application/octet-stream" },
    });
  };
}

export default function PageEmptyState({ message }: { message: string }) {
  return <span>{message}</span>;
}
