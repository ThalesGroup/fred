// @vitest-environment happy-dom
// Copyright Thales 2026. Licensed under the Apache License, Version 2.0.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import SkillUsageTable from "./SkillUsageTable";
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
it("sorts usage numerically, preserves origin columns and shows request states", () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const data = {
    since: "2026-10-01T00:00:00Z",
    until: "2026-10-07T00:00:00Z",
    truncated: true,
    rows: [
      { skill_name: "alpha", user_count: 12, model_count: 1, total: 13 },
      { skill_name: "beta", user_count: 2, model_count: 8, total: 10 },
    ],
  };
  try {
    act(() => root.render(<SkillUsageTable data={data} isLoading={false} isError={false} />));
    expect(container.textContent).toContain("rework.analytics.skillUsage.model_count");
    expect(container.textContent).toContain("rework.analytics.skillUsage.truncated");
    const button = [...container.querySelectorAll("button")].find((b) =>
      b.textContent?.includes("rework.analytics.skillUsage.user_count"),
    )!;
    act(() => button.click());
    expect([...container.querySelectorAll('[title="alpha"], [title="beta"]')].map((e) => e.textContent)).toEqual([
      "beta",
      "alpha",
    ]);
    act(() => button.click());
    expect([...container.querySelectorAll('[title="alpha"], [title="beta"]')].map((e) => e.textContent)).toEqual([
      "alpha",
      "beta",
    ]);
    act(() => root.render(<SkillUsageTable data={data} isLoading={false} isError />));
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("common.loadingError");
    expect(container.querySelector('[title="alpha"]')).toBeNull();
    act(() => root.render(<SkillUsageTable isLoading isError={false} />));
    expect(container.querySelector('[role="status"]')?.textContent).toBe("common.loading");
    act(() => root.render(<SkillUsageTable data={{ ...data, rows: [] }} isLoading={false} isError={false} />));
    expect(container.querySelector('[role="status"]')?.textContent).toBe("rework.analytics.skillUsage.empty");
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});
