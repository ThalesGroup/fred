// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { runtimeExecuteStreamPath } from "./runtimeExecutionUrl";

const VALID_PATH = "/runtime/agents-v2/agents/execute/stream";

describe("runtimeExecuteStreamPath", () => {
  it("accepts a canonical same-origin execution path", () => {
    expect(runtimeExecuteStreamPath(VALID_PATH)).toBe(VALID_PATH);
  });

  it.each([
    "https://outside.example/agents/execute/stream",
    "//outside.example/agents/execute/stream",
    "/runtime/../outside/agents/execute/stream",
    "/runtime/%2foutside/agents/execute/stream",
    "/runtime\\outside/agents/execute/stream",
    "/runtime//agents/execute/stream",
    "/runtime/agents/execute/stream?next=outside",
    "/runtime/agents/execute/stream#outside",
    "/control-plane/v1/admin/delete",
  ])("rejects an unsafe execution URL: %s", (candidate) => {
    expect(() => runtimeExecuteStreamPath(candidate)).toThrow("Invalid runtime execution URL");
  });
});
