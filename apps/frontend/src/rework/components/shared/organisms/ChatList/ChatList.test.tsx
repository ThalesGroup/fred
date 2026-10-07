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

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

let agents: { agent_instance_id: string; display_name: string }[] | undefined;
let success = true;
let error = false;
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: vi.fn() }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery: () => ({
    data: [
      {
        session_id: "saved",
        agent_instance_id: "agent-1",
        title: "Preserved conversation",
      },
    ],
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
  ChatListItem: (props: { href: string; label: string; agentName?: string }) => (
    <a href={props.href}>
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
    expect(html).toContain("(deleted)");
    expect(html).toContain("/team/team-1/managed-chat/agent-1?session=saved");
  });
  it.each([
    [undefined, false, false],
    [[], false, true],
  ] as const)("does not label unresolved or failed catalog reads as deletion (%s)", (data, resolved, failed) => {
    agents = data;
    success = resolved;
    error = failed;
    expect(renderToStaticMarkup(<ChatList teamId="team-1" />)).not.toContain("(deleted)");
  });
  it("returns to a live agent label once the next team's catalog resolves", () => {
    agents = [{ agent_instance_id: "agent-1", display_name: "Assistant" }];
    success = true;
    error = false;
    const html = renderToStaticMarkup(<ChatList teamId="team-2" />);
    expect(html).toContain("Assistant");
    expect(html).not.toContain("(deleted)");
  });
});
