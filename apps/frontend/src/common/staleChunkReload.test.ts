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

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installStaleChunkReload } from "./staleChunkReload";

describe("installStaleChunkReload", () => {
  const reload = vi.fn();
  let target: EventTarget;
  let storage: Map<string, string>;

  const fakeWindow = () =>
    Object.assign(target, {
      sessionStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => void storage.set(key, value),
      },
      location: { reload },
    }) as unknown as Window;

  const fire = () => {
    const event = new Event("vite:preloadError", { cancelable: true });
    target.dispatchEvent(event);
    return event;
  };

  beforeEach(() => {
    vi.useFakeTimers();
    reload.mockClear();
    target = new EventTarget();
    storage = new Map();
    installStaleChunkReload(fakeWindow());
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reloads once and swallows the error", () => {
    const event = fire();

    expect(reload).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("lets a second failure right after the reload surface instead of looping", () => {
    fire();
    const second = fire();

    expect(reload).toHaveBeenCalledTimes(1);
    expect(second.defaultPrevented).toBe(false);
  });

  it("reloads again for a later deploy, once the guard has expired", () => {
    fire();
    vi.advanceTimersByTime(60_001);
    fire();

    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("does not reload when the guard cannot be stored", () => {
    target = new EventTarget();
    const win = Object.assign(target, {
      sessionStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
      },
      location: { reload },
    }) as unknown as Window;
    installStaleChunkReload(win);

    const event = fire();

    expect(reload).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });
});
