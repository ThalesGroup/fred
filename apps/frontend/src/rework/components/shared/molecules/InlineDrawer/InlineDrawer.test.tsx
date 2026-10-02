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

import { renderToStaticMarkup } from "react-dom/server";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { DialogPrimitive } from "../Dialog/DialogPrimitive";
import { afterEach, expect, it, vi } from "vitest";
import { InlineDrawer, type InlineDrawerProps } from "./InlineDrawer";

const props: InlineDrawerProps = {
  open: true,
  onClose: () => {},
  title: "Drawer",
  layout: "push",
  resizable: { persistKey: "width-test", maxViewportFraction: 0.8 },
};

afterEach(() => localStorage.clear());

it("keeps fractional pixel widths and prefers a persisted drag width", () => {
  expect(renderToStaticMarkup(<InlineDrawer {...props} width="480.5px" />)).toContain(
    "--drawer-width:min(480.5px, 80vw)",
  );
  localStorage.setItem("localHook:inline-drawer:width-test:width", "520");
  expect(renderToStaticMarkup(<InlineDrawer {...props} width="480.5px" />)).toContain(
    "--drawer-width:min(520px, 80vw)",
  );
});

it.each(["30rem", "50%", "30vw", "calc(100px + 20vw)"])(
  "rejects %s from untyped resizable consumers instead of silently treating it as pixels",
  (width) => {
    const untypedProps = { ...props, width } as InlineDrawerProps;
    expect(() => renderToStaticMarkup(<InlineDrawer {...untypedProps} />)).toThrow("resizable width must use pixels");
  },
);

it("keeps CSS widths available without resizing", () => {
  expect(renderToStaticMarkup(<InlineDrawer open onClose={() => {}} title="Overlay" width="30rem" />)).toContain(
    "--drawer-width:30rem",
  );
});

it.each([undefined, "overlay"])("rejects resizing with layout %s", (layout) => {
  const invalid = { ...props, layout } as unknown as InlineDrawerProps;
  expect(() => renderToStaticMarkup(<InlineDrawer {...invalid} />)).toThrow('resizable requires layout="push"');
});

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
it.each([false, true])("Escape closes only the dialog with initially open child=%s", async (initiallyOpen) => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const parent = vi.fn();
  const child = vi.fn();
  function Harness() {
    const [open, setOpen] = useState(initiallyOpen);
    return (
      <div className="fred-ui">
        <InlineDrawer open title="Parent" onClose={parent}>
          <button onClick={() => setOpen(true)}>Open child</button>
          <DialogPrimitive
            open={open}
            title="Child"
            confirmLabel="Save"
            onConfirm={() => {}}
            onCancel={() => {
              child();
              setOpen(false);
            }}
          >
            <input />
          </DialogPrimitive>
        </InlineDrawer>
      </div>
    );
  }
  try {
    act(() => root.render(<Harness />));
    const trigger = Array.from(host.querySelectorAll("button")).find((button) => button.textContent === "Open child")!;
    for (let cycle = 0; cycle < 2; cycle++) {
      if (!initiallyOpen || cycle > 0)
        act(() => {
          trigger.focus();
          trigger.click();
        });
      const field = document.querySelector("input")!;
      await act(async () => {
        field.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      expect(child).toHaveBeenCalledTimes(cycle + 1);
      expect(parent).not.toHaveBeenCalled();
      expect(document.querySelector('[role="dialog"] input')).toBeNull();
    }
    await act(async () => {
      trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(parent).toHaveBeenCalledOnce();
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});

it("keyboard resizing shares pointer bounds and persists its width", () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  try {
    act(() =>
      root.render(
        <InlineDrawer
          {...props}
          width="400px"
          resizable={{ persistKey: "keys", minWidth: 320, maxWidth: 500, maxViewportFraction: 1 }}
          resizeLabel="Resize details"
        />,
      ),
    );
    const handle = host.querySelector('[role="separator"]') as HTMLElement;
    const key = (key: string) =>
      act(() => handle.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })));
    expect(handle.tabIndex).toBe(0);
    expect(handle.getAttribute("aria-label")).toBe("Resize details");
    key("ArrowLeft");
    expect(handle.getAttribute("aria-valuenow")).toBe("410");
    key("ArrowRight");
    expect(handle.getAttribute("aria-valuenow")).toBe("400");
    key("End");
    key("ArrowLeft");
    expect(handle.getAttribute("aria-valuenow")).toBe("500");
    key("Home");
    key("ArrowRight");
    expect(handle.getAttribute("aria-valuenow")).toBe("320");
    expect(localStorage.getItem("localHook:inline-drawer:keys:width")).toBe("320");
  } finally {
    act(() => root.unmount());
  }
});

it.each([false, true])("Escape preserves the lower drawer (nested=%s)", async (nested) => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const lower = vi.fn(),
    upper = vi.fn();
  function Harness() {
    const [open, setOpen] = useState(true);
    const detail = (
      <InlineDrawer
        open={open}
        title="Detail"
        onClose={() => {
          upper();
          setOpen(false);
        }}
      >
        <input />
      </InlineDrawer>
    );
    return (
      <>
        <InlineDrawer open layout="push" title="Base" onClose={lower}>
          <button onClick={() => setOpen(true)}>Reopen</button>
          {nested && detail}
        </InlineDrawer>
        {!nested && detail}
      </>
    );
  }
  try {
    act(() => root.render(<Harness />));
    for (let cycle = 0; cycle < 2; cycle++) {
      if (cycle)
        act(() =>
          Array.from(host.querySelectorAll("button"))
            .find((b) => b.textContent === "Reopen")!
            .click(),
        );
      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", cancelable: true }));
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      expect(upper).toHaveBeenCalledTimes(cycle + 1);
      expect(lower).not.toHaveBeenCalled();
    }
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(lower).toHaveBeenCalledOnce();
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});
it("peer overlays use paint order, independently of listener re-registration", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const first = vi.fn(),
    last = vi.fn();
  const view = (callback: () => void) => (
    <>
      <InlineDrawer open title="First" onClose={callback} />
      <InlineDrawer open title="Last" onClose={last} />
    </>
  );
  try {
    act(() => root.render(view(first)));
    act(() => root.render(view(() => first())));
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(last).toHaveBeenCalledOnce();
    expect(first).not.toHaveBeenCalled();
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});

it.each([false, true])("blocks lower drawer controls and restores them on close, nested=%s", (nested) => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const view = (open: boolean) => {
    const upper = (
      <InlineDrawer title="Upper" open={open} onClose={() => {}} width="200px">
        <button>Upper action</button>
      </InlineDrawer>
    );
    return (
      <>
        <InlineDrawer title="Lower" open onClose={() => {}} width="600px">
          <button data-lower data-open="false">
            Lower action
          </button>
          {nested && upper}
        </InlineDrawer>
        {!nested && upper}
      </>
    );
  };
  try {
    act(() => root.render(view(true)));
    const lower = host.querySelector<HTMLElement>("[data-lower]")!;
    const upper = Array.from(host.querySelectorAll("button")).find((el) => el.textContent === "Upper action")!;
    expect(lower.closest("[inert]")).not.toBeNull();
    expect(upper.closest("[inert]")).toBeNull();
    act(() => root.render(view(false)));
    expect(lower.closest("[inert]")).toBeNull();
    expect(upper.closest("[inert]")).not.toBeNull();
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});

it("keeps a lower drawer inert if it closes underneath an overlay", () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const view = (lowerOpen: boolean, upperOpen: boolean) => (
    <>
      <InlineDrawer title="Lower" open={lowerOpen} onClose={() => {}}>
        Lower
      </InlineDrawer>
      <InlineDrawer title="Upper" open={upperOpen} onClose={() => {}}>
        Upper
      </InlineDrawer>
    </>
  );
  try {
    act(() => root.render(view(true, true)));
    act(() => root.render(view(false, true)));
    act(() => root.render(view(false, false)));
    expect(host.querySelector("aside")?.inert).toBe(true);
    expect((host.querySelector("aside")?.previousElementSibling as HTMLElement).inert).toBe(true);
    act(() => root.render(view(true, false)));
    expect(host.querySelector("aside")?.inert).toBe(false);
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});

it("closes inside a form without submitting", () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const submit = vi.fn((event: React.FormEvent) => event.preventDefault());
  const close = vi.fn();
  try {
    act(() =>
      root.render(
        <form onSubmit={submit}>
          <InlineDrawer open title="Edit" onClose={close} />
        </form>,
      ),
    );
    act(() => host.querySelector<HTMLButtonElement>('button[aria-label="Close panel"]')!.click());
    expect(close).toHaveBeenCalledOnce();
    expect(submit).not.toHaveBeenCalled();
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});

it("contains overlay focus and restores the opener after closing", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button data-opener onClick={() => setOpen(true)}>
          Open
        </button>
        <button data-outside>Outside</button>
        <InlineDrawer title="Modal" open={open} onClose={() => setOpen(false)}>
          <input aria-label="Last field" />
        </InlineDrawer>
      </>
    );
  }
  try {
    act(() => root.render(<Harness />));
    const opener = host.querySelector<HTMLButtonElement>("[data-opener]")!;
    act(() => {
      opener.focus();
      opener.click();
    });
    const close = host.querySelector<HTMLButtonElement>('button[aria-label="Close panel"]')!;
    const input = host.querySelector<HTMLInputElement>("input")!;
    expect(document.activeElement).toBe(close);
    act(() =>
      close.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true }),
      ),
    );
    expect(document.activeElement).toBe(input);
    act(() => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true })));
    expect(document.activeElement).toBe(close);
    act(() => host.querySelector<HTMLButtonElement>("[data-outside]")!.focus());
    expect(document.activeElement).toBe(close);
    await act(async () => close.click());
    expect(document.activeElement).toBe(opener);
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});

it.each(["overlay", "push"] as const)("announces %s drawer semantics", (layout) => {
  const host = document.createElement("div");
  host.innerHTML = renderToStaticMarkup(<InlineDrawer open layout={layout} title="Details" onClose={() => {}} />);
  const drawer = host.querySelector("aside")!;
  expect(drawer.getAttribute("role")).toBe(layout === "overlay" ? "dialog" : null);
  expect(drawer.getAttribute("aria-modal")).toBe(layout === "overlay" ? "true" : null);
  expect(host.querySelector('[id="' + drawer.getAttribute("aria-labelledby") + '"]')?.textContent).toBe("Details");
});

it("retains a pending Escape across a parent rerender and calls the latest handler", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const first = vi.fn();
  const latest = vi.fn();
  try {
    act(() => root.render(<InlineDrawer open title="Panel" onClose={first} />));
    act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", cancelable: true })));
    act(() => root.render(<InlineDrawer open title="Updated panel" onClose={latest} />));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
    });
    expect(first).not.toHaveBeenCalled();
    expect(latest).toHaveBeenCalledOnce();
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});
