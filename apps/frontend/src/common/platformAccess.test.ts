// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("./config", () => ({ getConfig: () => ({ frontend_basename: "/fred/" }) }));
import {
  handlePlatformAccessDenial,
  isPlatformAccessStandalone,
  platformPath,
  platformAccessDenied,
} from "./platformAccess";

beforeEach(() => window.history.replaceState({}, "", "/fred/home"));
describe("platform admission routes", () => {
  it("uses the configured basename and recognizes standalone paths", () => {
    expect(platformPath("/join-free/token")).toBe("/fred/join-free/token");
    expect(isPlatformAccessStandalone()).toBe(false);
    window.history.replaceState({}, "", "/fred/join-free/token");
    expect(isPlatformAccessStandalone()).toBe(true);
  });
  it.each([
    [401, { detail: "platform_access_denied" }],
    [403, { detail: "user_not_accept_gcu" }],
    [403, { detail: "forbidden" }],
    [503, { detail: "platform_access_unavailable" }],
  ])("preserves an unrelated error %s", (status, body) => {
    const clear = vi.fn();
    window.addEventListener(platformAccessDenied, clear, { once: true });
    expect(handlePlatformAccessDenial(status, body)).toBe(false);
    expect(clear).not.toHaveBeenCalled();
    window.removeEventListener(platformAccessDenied, clear);
  });
  it("clears protected state on an admission denial without looping on the denial page", () => {
    window.history.replaceState({}, "", "/fred/platform-access-denied");
    const clear = vi.fn();
    window.addEventListener(platformAccessDenied, clear, { once: true });
    expect(handlePlatformAccessDenial(403, { detail: "platform_access_denied" })).toBe(true);
    expect(clear).toHaveBeenCalledOnce();
    expect(window.location.pathname).toBe("/fred/platform-access-denied");
  });
});
