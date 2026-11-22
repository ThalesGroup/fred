// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type { ProposeWikiFileRequest } from "../../../slices/controlPlane/controlPlaneOpenApi";

export interface WikiShareFile {
  key: string;
  name: string;
  prepareWikiShare: () => Promise<ProposeWikiFileRequest>;
}

export async function sha256(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
