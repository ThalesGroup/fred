// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import type { SelfTestFamily } from "../../../../features/pipeline/familyCatalog";
import { SelfTestView } from "./SelfTestView";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@shared/molecules/PageHeader/PageHeader.tsx", () => ({
  default: ({ actions }: { actions: React.ReactNode }) => <header>{actions}</header>,
}));
vi.mock("@shared/molecules/ServiceNotice/ServiceNotice.tsx", () => ({ default: () => null }));

vi.mock("./FamilySection", () => ({ FamilySection: () => <section>Family</section> }));
vi.mock("@shared/atoms/Button/Button.tsx", () => ({
  default: ({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled: boolean }) => (
    <button onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
}));

it("collapses each level at the start and preserves sections opened during the run", async () => {
  const element = document.createElement("div");
  const root = createRoot(element);
  let finish!: () => void;
  const first: SelfTestFamily = {
    id: "platform",
    icon: "cloud",
    run: {
      steps: [],
      isRunning: false,
      start: () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    },
  };
  const groups = ["Shared checks", "Organization", "Team", "Project", "Personal"].map((title, index) => ({
    id: title,
    title,
    families: index === 0 ? [first] : [],
  }));
  const render = () => root.render(<SelfTestView groups={groups} setup={() => null} />);
  const levels = () => Array.from(element.querySelectorAll("details"), (section) => section.open);
  const toggle = (index: number) => element.querySelectorAll("summary")[index].click();
  try {
    await act(async () => render());
    expect(levels()).toEqual([false, false, false, false, false]);
    expect(element.querySelector("summary [role='progressbar']")).toBeNull();
    await act(async () => groups.forEach((_, index) => toggle(index)));
    expect(levels()).toEqual([true, true, true, true, true]);

    await act(async () =>
      Array.from(element.querySelectorAll("button"))
        .find((button) => button.textContent === "rework.selftest.page.runPath")!
        .click(),
    );
    expect(levels()).toEqual([false, false, false, false, false]);
    await act(async () => {
      first.run.isRunning = true;
      render();
    });
    const activeSummary = element.querySelector("summary")!;
    expect(activeSummary.querySelector("[role='status']")?.textContent).toContain("running");
    expect(activeSummary.querySelector("[role='progressbar']")).not.toBeNull();
    expect(element.querySelectorAll("summary [role='progressbar']")).toHaveLength(1);
    expect(levels()).toEqual([false, false, false, false, false]);
    await act(async () => toggle(1));
    await act(async () => {
      first.run.steps = [{ id: "session", title: "Check session", status: "running" }];
      render();
    });
    expect(levels()).toEqual([false, true, false, false, false]);
    await act(async () => {
      first.run.isRunning = false;
      first.run.steps = [{ id: "session", title: "Check session", status: "passed" }];
      render();
      finish();
    });
    expect(levels()).toEqual([false, true, false, false, false]);
    expect(element.querySelector("summary [role='status']")?.textContent).toContain("sectionStatus.passed");
    expect(element.querySelector("summary [role='progressbar']")).toBeNull();
    expect(element.textContent).not.toContain("standardSummary");
  } finally {
    await act(async () => root.unmount());
  }
});

it.each([
  { statuses: [], expected: "notRun" },
  { statuses: ["skipped"], expected: "skipped" },
  { statuses: ["passed", "skipped"], expected: "passed" },
  { statuses: ["passed", "failed", "skipped"], expected: "failed" },
  { statuses: ["failed", "running"], expected: "running" },
] as const)("shows $expected in the collapsed section header", async ({ statuses, expected }) => {
  const element = document.createElement("div");
  const root = createRoot(element);
  const family: SelfTestFamily = {
    id: "platform",
    icon: "cloud",
    run: {
      steps: statuses.map((status, index) => ({ id: String(index), title: "Check", status })),
      isRunning: false,
      start: async () => {},
    },
  };
  try {
    await act(async () =>
      root.render(<SelfTestView groups={[{ id: "shared", title: "Shared checks", families: [family] }]} />),
    );
    expect(element.querySelector("details")?.open).toBe(false);
    expect(element.querySelector("summary [role='status']")?.textContent).toBe(
      `rework.selftest.report.sectionStatus.${expected}`,
    );
    expect(element.querySelector("summary")?.textContent).toContain("rework.selftest.report.counts");
    expect(!!element.querySelector("summary [role='progressbar']")).toBe(expected === "running");
  } finally {
    await act(async () => root.unmount());
  }
});

it.each(["unmount", "selection change"])(
  "runs sequentially with separate manual tests and stops after %s",
  async (stop) => {
    const order: string[] = [];
    let finish: () => void = () => {};
    const first = {
      id: "platform",
      icon: "cloud",
      run: {
        steps: [],
        isRunning: false,
        start: vi.fn(() => {
          order.push("shared");
          return new Promise<void>((resolve) => {
            finish = resolve;
          });
        }),
      },
    } as SelfTestFamily;
    const second = {
      id: "identity",
      icon: "person",
      run: {
        steps: [],
        isRunning: false,
        start: vi.fn(async () => {
          order.push("organization");
        }),
      },
    } as SelfTestFamily;
    const element = document.createElement("div");
    const root = createRoot(element);
    await act(async () => {
      root.render(
        <SelfTestView
          families={[]}
          groups={[
            { id: "shared", title: "Shared", families: [first] },
            { id: "org", title: "Organization", families: [second] },
          ]}
          manual={() => <div>Manual tests separate</div>}
        />,
      );
    });
    expect(element.textContent?.match(/Manual tests separate/g)).toHaveLength(1);
    const button = [...element.querySelectorAll("button")].find((candidate) =>
      candidate.textContent?.includes("rework.selftest.page.runPath"),
    );
    await act(async () => {
      button?.click();
    });
    expect(order).toEqual(["shared"]);
    await act(async () => {
      finish();
    });
    expect(order).toEqual(["shared", "organization"]);
    await act(async () => {
      button?.click();
    });
    await act(async () => {
      if (stop === "unmount") root.unmount();
      else
        root.render(
          <SelfTestView
            groups={[{ id: "different", title: "Another organization", families: [second] }]}
            manual={() => null}
          />,
        );
    });
    await act(async () => {
      finish();
    });
    expect(order).toEqual(["shared", "organization", "shared"]);
    if (stop !== "unmount")
      await act(async () => {
        root.unmount();
      });
  },
);
