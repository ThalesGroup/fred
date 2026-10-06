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

// The variety row: the switch saves "off" and restores the last mode, the
// selects save the mode and the max, and are disabled while off.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    options,
    ariaLabel,
    value,
    disabled,
    onChange,
  }: {
    options: { value: unknown; label: string }[];
    ariaLabel: string;
    value: unknown;
    disabled: boolean;
    onChange: (value: unknown) => void;
  }) => (
    <select
      aria-label={ariaLabel}
      value={String(value)}
      disabled={disabled}
      onChange={(e) => onChange(options.find((o) => String(o.value) === e.target.value)?.value)}
    >
      {options.map((o) => (
        <option key={String(o.value)} value={String(o.value)}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { PptBuilderVarietySettings } from "./PptBuilderVarietySettings";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const KEY = "capability.ppt_builder.fields.variety_check";

let container: HTMLDivElement;
let root: Root | null = null;
let saved: Record<string, unknown> = {};

function Harness({ initial }: { initial: Record<string, unknown> }) {
  const [values, setValues] = useState(initial);
  return (
    <PptBuilderVarietySettings
      disabled={false}
      configValues={values}
      onConfigChange={(key, value) => {
        saved = { ...saved, [key]: value };
        setValues((v) => ({ ...v, [key]: value }));
      }}
    />
  );
}

function render(initial: Record<string, unknown>) {
  saved = {};
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root?.render(<Harness initial={initial} />));
}

afterEach(() => {
  act(() => root?.unmount());
  container.remove();
  root = null;
});

const toggle = () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
const select = (aria: string) => container.querySelector<HTMLSelectElement>(`select[aria-label="${KEY}.${aria}"]`)!;

function pick(element: HTMLSelectElement, value: string) {
  act(() => {
    element.value = value;
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

describe("PptBuilderVarietySettings", () => {
  it("reads as one sentence with the mode and max selects", () => {
    render({});
    const text = container.textContent ?? "";
    for (const part of ["title", "atMost", "times", "options.template_slide", "options.kind", "description"]) {
      expect(text).toContain(`${KEY}.${part}`);
    }
    expect(toggle().checked).toBe(true);
    expect(select("modeAria").value).toBe("template_slide");
    expect(select("maxAria").value).toBe("2");
  });

  it("saves off when switched off, disables the selects, and restores the last mode", () => {
    render({ variety_check: "template_slide" });
    pick(select("modeAria"), "kind");
    expect(saved.variety_check).toBe("kind");
    act(() => toggle().click());
    expect(saved.variety_check).toBe("off");
    expect(select("modeAria").disabled).toBe(true);
    expect(select("maxAria").disabled).toBe(true);
    act(() => toggle().click());
    expect(saved.variety_check).toBe("kind");
    expect(select("modeAria").disabled).toBe(false);
  });

  it("switches on to the default mode when the stored value is off", () => {
    render({ variety_check: "off", variety_max_uses: 4 });
    expect(toggle().checked).toBe(false);
    expect(select("maxAria").value).toBe("4");
    act(() => toggle().click());
    expect(saved.variety_check).toBe("template_slide");
  });

  it("saves the max as a number", () => {
    render({ variety_check: "kind" });
    pick(select("maxAria"), "1");
    expect(saved.variety_max_uses).toBe(1);
  });
});
