// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import SearchableCheckboxPicker from "./SearchableCheckboxPicker";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const labels = {
  title: "",
  reset: "All",
  search: "Search",
  searchPlaceholder: "Search",
  clearSearch: "Clear search",
  selected: "Selected",
  others: "Others",
  empty: "No matches",
  cancel: "Cancel",
  apply: "Apply",
};

it("dismisses a picker when keyboard focus moves to its neighbor and gives Escape to the active picker", () => {
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  const escapeOutside = vi.fn();
  const onChange = vi.fn();
  window.addEventListener("keydown", escapeOutside);
  try {
    act(() =>
      root.render(
        <>
          <SearchableCheckboxPicker
            icon="group"
            labels={{ ...labels, title: "Teams" }}
            triggerLabel="Teams"
            options={[{ value: "blue", label: "Blue" }]}
            value={[]}
            onChange={onChange}
          />
          <SearchableCheckboxPicker
            icon="filter_list"
            labels={{ ...labels, title: "Outcomes" }}
            triggerLabel="Outcomes"
            options={[{ value: "failed", label: "Failed" }]}
            value={[]}
            onChange={onChange}
          />
        </>,
      ),
    );
    const [teams, outcomes] = host.querySelectorAll<HTMLButtonElement>('[aria-haspopup="dialog"]');
    act(() => {
      teams.focus();
      teams.click();
    });
    expect(document.activeElement).toBe(host.querySelector('[aria-label="Teams"] input'));

    act(() => outcomes.focus());
    expect(teams.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(outcomes);

    act(() => outcomes.click());
    const outcome = host.querySelector<HTMLInputElement>('[aria-label="Outcomes"] input[type="checkbox"]');
    act(() => outcome?.focus());
    expect(document.activeElement).toBe(outcome);
    expect(outcomes.getAttribute("aria-expanded")).toBe("true");

    act(() => {
      document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(escapeOutside).not.toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
    expect(outcomes.getAttribute("aria-expanded")).toBe("false");
    expect(teams.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(outcomes);
  } finally {
    window.removeEventListener("keydown", escapeOutside);
    act(() => root.unmount());
    host.remove();
  }
});
