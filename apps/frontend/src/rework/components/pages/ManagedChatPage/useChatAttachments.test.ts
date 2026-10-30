// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import type { Attachment } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { attachmentStatus } from "./useChatAttachments";

describe("server attachment readiness", () => {
  it.each(["sales.csv", "workbook.xlsx"])("accepts %s ready with zero vectors", (name) => {
    expect(attachmentStatus({ name, ready: true, processing: { status: "succeeded", vectors: 0 } } as Attachment)).toBe(
      "ready",
    );
  });
  it("does not derive readiness from processing success or a missing processing attempt", () => {
    expect(attachmentStatus({ ready: false, processing: { status: "succeeded" } } as Attachment)).toBe("error");
    expect(attachmentStatus({ ready: false, processing: null } as Attachment)).toBe("error");
  });
});
