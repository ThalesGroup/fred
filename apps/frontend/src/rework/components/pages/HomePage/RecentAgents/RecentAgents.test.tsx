import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const query = vi.hoisted(() => ({
  data: { agents: [] as { agent_instance_id: string; team_id: string }[], history_unavailable: false },
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({ useHomeAgentsQuery: () => query }));
vi.mock("../../../../../hooks/useFrontendBootstrap", () => ({ useFrontendBootstrap: () => ({ availableTeams: [] }) }));
vi.mock("@shared/atoms/Icon/Icon.tsx", () => ({ default: () => null }));
vi.mock("@shared/atoms/Button/Button.tsx", () => ({
  default: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
}));
vi.mock("./CompactAgentCard.tsx", () => ({
  default: ({ instance }: { instance: { agent_instance_id: string } }) => <span>{instance.agent_instance_id}</span>,
}));
import RecentAgents from "./RecentAgents";

describe("Home agents discovery states", () => {
  it("distinguishes loading and errors from a successful empty result", () => {
    query.isLoading = true;
    expect(renderToStaticMarkup(<RecentAgents />)).toContain("recentAgents.loading");
    query.isLoading = false;
    query.isError = true;
    const failed = renderToStaticMarkup(<RecentAgents />);
    expect(failed).toContain("recentAgents.error");
    expect(failed).toContain("recentAgents.retry");
    expect(failed).not.toContain("recentAgents.empty");
    query.isError = false;
    expect(renderToStaticMarkup(<RecentAgents />)).toContain("recentAgents.empty");
  });

  it("keeps suggestions visible when history is unavailable and preserves server ordering", () => {
    query.data = {
      agents: ["z", "a", "b", "c", "d"].map((id) => ({ agent_instance_id: id, team_id: "personal-alice" })),
      history_unavailable: true,
    };
    const html = renderToStaticMarkup(<RecentAgents />);
    expect(html).toContain("recentAgents.historyUnavailable");
    expect(html).toContain('data-count="5"');
    expect(html.indexOf(">z<")).toBeLessThan(html.indexOf(">a<"));
  });
});
