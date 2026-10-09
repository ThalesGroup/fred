// @vitest-environment happy-dom
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

import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const defaultSessions = [
  {
    session_id: "saved",
    agent_instance_id: "agent-1",
    title: "Preserved conversation",
    agent_display_name: "Preserved assistant",
  },
];
let sessions = defaultSessions;
let agents: { agent_instance_id: string; display_name: string }[] | undefined;
let success = true;
let error = false;
vi.mock("../../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "Lumi" }),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: vi.fn() }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery: () => ({
    data: sessions,
    isLoading: false,
  }),
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery: () => ({
    currentData: agents,
    isSuccess: success,
    isError: error,
    refetch: vi.fn(),
  }),
  useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation: () => [vi.fn()],
}));
vi.mock("./ChatListItem/ChatListItem.tsx", () => ({
  ChatListItem: (props: { href: string; label: string; agentName?: string; agentDeleted?: boolean }) => (
    <a href={props.href} data-agent-deleted={props.agentDeleted}>
      {props.label} - {props.agentName}
    </a>
  ),
}));
import ChatList from "./ChatList";

describe("ChatList deleted agents", () => {
  it("keeps the saved conversation navigable and labels a confirmed deleted agent", () => {
    agents = [];
    success = true;
    error = false;
    const html = renderToStaticMarkup(<ChatList teamId="team-1" />);
    expect(html).toContain("Preserved conversation");
    expect(html).toContain("Preserved assistant");
    expect(html).toContain('data-agent-deleted="true"');
    expect(html).not.toContain("(deleted)");
    expect(html).toContain("/team/team-1/managed-chat/agent-1?session=saved");
  });
  it.each([
    [undefined, false, false],
    [[], false, true],
  ] as const)("does not label unresolved or failed catalog reads as deletion (%s)", (data, resolved, failed) => {
    agents = data;
    success = resolved;
    error = failed;
    const html = renderToStaticMarkup(<ChatList teamId="team-1" />);
    expect(html).toContain("Preserved assistant");
    expect(html).not.toContain('data-agent-deleted="true"');
  });
  it("returns to a live agent label once the next team's catalog resolves", () => {
    agents = [{ agent_instance_id: "agent-1", display_name: "Assistant" }];
    success = true;
    error = false;
    const html = renderToStaticMarkup(<ChatList teamId="team-2" />);
    expect(html).toContain("Assistant");
    expect(html).not.toContain('data-agent-deleted="true"');
  });
});

it("groups by agent identity while preserving distinct live and deleted names", () => {
  agents = [{ agent_instance_id: "live", display_name: "Same name" }];
  success = true;
  error = false;
  sessions = [
    {
      session_id: "saved",
      agent_instance_id: "agent-1",
      title: "Deleted conversation",
      agent_display_name: "Same name",
    },
    { session_id: "other", agent_instance_id: "live", title: "Live conversation", agent_display_name: "Old live name" },
  ];
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    act(() => root.render(<ChatList teamId="team-1" />));
    act(() =>
      container.querySelector<HTMLButtonElement>('button[aria-label="rework.sidebar.chatList.groupByAgent"]')!.click(),
    );
    const headers = container.querySelectorAll('[class*="groupHeader"]');
    expect(headers).toHaveLength(2);
    expect([...headers].map((header) => header.textContent)).toEqual(["Same name", "Same name"]);
    expect(container.querySelectorAll('[class*="groupHeader"][data-agent-deleted="true"]')).toHaveLength(1);
    expect(container.textContent).toContain("Deleted conversation");
    expect(container.textContent).toContain("Live conversation");
  } finally {
    act(() => root.unmount());
    container.remove();
    sessions = defaultSessions;
  }
});
