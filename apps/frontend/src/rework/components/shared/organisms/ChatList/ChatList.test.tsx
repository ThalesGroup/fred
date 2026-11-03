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
import { beforeEach, expect, it, vi } from "vitest";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const defaultSession = {
  session_id: "saved",
  agent_instance_id: "agent-1",
  title: "Preserved conversation",
  agent_display_name: "Preserved assistant",
  agent_deleted: false,
};
let sessions: (typeof defaultSession)[] | undefined;
let loading = false;
let error: { status: number } | undefined;
const readSessions = vi.hoisted(() => vi.fn());
vi.mock("../../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "" }),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const navigate = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: vi.fn() }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useListSessionsQuery: (args: unknown, options: unknown) => {
    readSessions(args, options);
    return { currentData: sessions, isFetching: loading, error, isError: !!error, refetch: vi.fn() };
  },
  useDeleteSessionMutation: () => [vi.fn()],
}));
vi.mock("./ChatListItem/ChatListItem.tsx", () => ({
  ChatListItem: (props: {
    href: string;
    label: string;
    agentName?: string;
    agentTooltipName?: string;
    agentDeleted?: boolean;
  }) => (
    <a href={props.href} data-agent-deleted={props.agentDeleted} data-agent-tooltip-name={props.agentTooltipName}>
      {props.label} - {props.agentName}
    </a>
  ),
}));
import ChatList from "./ChatList";
import { abortTurn, registerTurn, settleTurn, type LiveTurn } from "@core/hooks/backgroundTurns";

beforeEach(() => {
  sessions = [{ ...defaultSession }];
  loading = false;
  error = undefined;
  readSessions.mockClear();
});

it("uses the canonical space and keeps a deleted agent's saved conversation navigable", () => {
  sessions = [{ ...defaultSession, agent_deleted: true }];
  const html = renderToStaticMarkup(<ChatList teamId="team-1" spaceId="space-1" />);
  expect(readSessions).toHaveBeenCalledWith({ spaceId: "space-1" }, expect.objectContaining({ skip: false }));
  expect(html).toContain("Preserved conversation");
  expect(html).toContain("Preserved assistant");
  expect(html).toContain('data-agent-deleted="true"');
  expect(html).toContain("/team/team-1/managed-chat/agent-1?session=saved");
});

it("uses the live name and deletion fact returned with the current session", () => {
  sessions = [{ ...defaultSession, agent_display_name: "Current assistant" }];
  const html = renderToStaticMarkup(<ChatList teamId="team-2" spaceId="space-2" />);
  expect(html).toContain("Current assistant");
  expect(html).not.toContain('data-agent-deleted="true"');
});

it("shows loading rather than inferring deletion from an unresolved read", () => {
  sessions = undefined;
  loading = true;
  const html = renderToStaticMarkup(<ChatList teamId="team-1" spaceId="space-1" />);
  expect(html).toContain("rework.sidebar.chatList.loading");
  expect(html).not.toContain('data-agent-deleted="true"');
});

it("keeps the list without a loading row during a refetch", () => {
  loading = true;
  const html = renderToStaticMarkup(<ChatList teamId="team-1" spaceId="space-1" />);
  expect(html).toContain("Preserved conversation");
  expect(html).not.toContain("rework.sidebar.chatList.loading");
});

it("keeps the list through a failed poll", () => {
  error = { status: 503 };
  const html = renderToStaticMarkup(<ChatList teamId="team-1" spaceId="space-1" />);
  expect(html).toContain("Preserved conversation");
  expect(html).not.toContain("chatbot.historyUnavailable");
});

it("shows the unavailable state when a failed read left no data", () => {
  sessions = undefined;
  error = { status: 503 };
  const html = renderToStaticMarkup(<ChatList teamId="team-1" spaceId="space-1" />);
  expect(html).toContain("chatbot.historyUnavailable");
});

it("hides retained session metadata after a refused read", () => {
  sessions = [{ ...defaultSession, agent_deleted: true }];
  error = { status: 403 };
  const html = renderToStaticMarkup(<ChatList teamId="team-1" spaceId="space-1" />);
  expect(html).not.toContain("Preserved conversation");
  expect(html).not.toContain("Preserved assistant");
  expect(html).not.toContain('data-agent-deleted="true"');
  expect(html).toContain("chatbot.historyUnavailable");
});

it("does not use a legacy team id as authority when the space is unresolved", () => {
  const html = renderToStaticMarkup(<ChatList teamId="team-1" />);
  expect(readSessions).toHaveBeenCalledWith({ spaceId: "" }, expect.objectContaining({ skip: true }));
  expect(html).not.toContain("Preserved conversation");
});

it("groups by agent identity while preserving distinct live and deleted names", () => {
  sessions = [
    { ...defaultSession, title: "Deleted conversation", agent_display_name: "Same name", agent_deleted: true },
    {
      ...defaultSession,
      session_id: "other",
      agent_instance_id: "live",
      title: "Live conversation",
      agent_display_name: "Same name",
    },
  ];
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    act(() => root.render(<ChatList teamId="team-1" spaceId="space-1" />));
    act(() =>
      container.querySelector<HTMLButtonElement>('button[aria-label="rework.sidebar.chatList.groupByAgent"]')!.click(),
    );
    const headers = container.querySelectorAll('[class*="groupHeader"]');
    expect(headers).toHaveLength(2);
    expect([...headers].map((header) => header.textContent)).toEqual([
      "Same name chatbot.deletedAgentSuffix",
      "Same name",
    ]);
    expect(container.querySelectorAll('[class*="groupHeader"][data-agent-deleted="true"]')).toHaveLength(1);
    expect(container.querySelector('a[data-agent-deleted="true"]')?.getAttribute("data-agent-tooltip-name")).toBe(
      "Same name",
    );
    expect(container.textContent).toContain("Deleted conversation");
    expect(container.textContent).toContain("Live conversation");
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});

it("announces a turn that ended out of sight with its title and a way to open it", () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  const turn = (awaitingInput: boolean): LiveTurn => ({
    sessionId: "saved",
    controller: new AbortController(),
    steeringTurnId: "steering",
    thoughts: new Map(),
    host: null,
    messages: [],
    detachedCallbacks: {},
    awaitingInput,
  });
  try {
    act(() => root.render(<ChatList teamId="team-1" />));
    for (const awaitingInput of [false, true]) {
      const finished = turn(awaitingInput);
      registerTurn(finished);
      settleTurn(finished);
    }
    expect(showInfo.mock.calls.map(([toast]) => [toast.summary, toast.detail])).toEqual([
      ["rework.sidebar.chatList.answerReady", "Preserved conversation"],
      ["rework.sidebar.chatList.awaitingInput", "Preserved conversation"],
    ]);
    showInfo.mock.calls[0][0].action.onClick();
    expect(navigate).toHaveBeenCalledWith("/team/team-1/managed-chat/agent-1?session=saved");
  } finally {
    act(() => root.unmount());
    abortTurn("saved");
  }
});
