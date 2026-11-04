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

// The plan-validation switch: off by default, saves a boolean.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { PptBuilderPlanSettings } from "./PptBuilderPlanSettings";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const KEY = "capability.ppt_builder.fields.validate_plan";

let container: HTMLDivElement;
let root: Root | null = null;
let saved: Record<string, unknown> = {};

function Harness({ initial, disabled = false }: { initial: Record<string, unknown>; disabled?: boolean }) {
  const [values, setValues] = useState(initial);
  return (
    <PptBuilderPlanSettings
      disabled={disabled}
      configValues={values}
      onConfigChange={(key, value) => {
        saved = { ...saved, [key]: value };
        setValues((v) => ({ ...v, [key]: value }));
      }}
    />
  );
}

function render(initial: Record<string, unknown>, disabled = false) {
  saved = {};
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root?.render(<Harness initial={initial} disabled={disabled} />));
}

afterEach(() => {
  act(() => root?.unmount());
  container.remove();
  root = null;
});

const toggle = () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;

describe("PptBuilderPlanSettings", () => {
  it("is off by default and shows its title and description", () => {
    render({});
    expect(toggle().checked).toBe(false);
    expect(container.textContent).toContain(`${KEY}.title`);
    expect(container.textContent).toContain(`${KEY}.description`);
  });

  it("saves true when switched on and false when switched off", () => {
    render({});
    act(() => toggle().click());
    expect(saved.validate_plan).toBe(true);
    act(() => toggle().click());
    expect(saved.validate_plan).toBe(false);
  });

  it("shows a stored value and follows the form's disabled state", () => {
    render({ validate_plan: true }, true);
    expect(toggle().checked).toBe(true);
    expect(toggle().disabled).toBe(true);
  });
});
