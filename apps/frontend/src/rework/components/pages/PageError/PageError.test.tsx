// @vitest-environment happy-dom

import { act } from "react";
import { createRoot } from "react-dom/client";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RouteError } from "./PageError.tsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function useBrokenHook() {
  throw new Error("private hook diagnostic");
}

function BrokenPage() {
  useBrokenHook();
  return null;
}

describe("RouteError", () => {
  it("shows a friendly page for a hook failure and lets the user return home", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const router = createMemoryRouter(
      [
        { path: "/broken", element: <BrokenPage />, errorElement: <RouteError /> },
        { path: "/", element: <p>Home ready</p> },
      ],
      { initialEntries: ["/broken"] },
    );

    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      await act(async () => root.render(<RouterProvider router={router} />));
      expect(container.querySelector("h1")?.textContent).toBe("pageError.unexpected");
      expect(container.textContent).toContain("pageError.unexpectedDescription");
      expect(container.textContent).toContain("pageError.retry");
      const details = container.querySelector("details");
      expect(details?.open).toBe(false);
      expect(details?.querySelector("summary")?.textContent).toBe("pageError.technicalDetails");
      expect(details?.querySelector("pre")?.textContent).toContain("private hook diagnostic");
      expect(details?.querySelector("pre")?.textContent).toContain("useBrokenHook");

      await act(async () => details?.querySelector("summary")?.click());
      expect(details?.open).toBe(true);

      const home = [...container.querySelectorAll("button")].find((button) =>
        button.textContent?.includes("pageError.message"),
      );
      expect(home).toBeDefined();
      await act(async () => home!.click());
      expect(container.textContent).toContain("Home ready");
    } finally {
      act(() => root.unmount());
      vi.restoreAllMocks();
    }
  });
});
