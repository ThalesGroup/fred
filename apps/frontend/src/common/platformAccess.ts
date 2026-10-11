// SPDX-License-Identifier: Apache-2.0
import { getConfig } from "./config";

export const platformAccessDenied = "platform-access/denied";

export function platformPath(path: string): string {
  const base = getConfig()?.frontend_basename ?? "/";
  return `${base.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

export function isPlatformAccessStandalone(): boolean {
  const path = window.location.pathname;
  return path === platformPath("platform-access-denied") || path.startsWith(platformPath("join-free/"));
}

export function handlePlatformAccessDenial(status: unknown, body: unknown): boolean {
  if (
    status !== 403 ||
    !body ||
    typeof body !== "object" ||
    !("detail" in body) ||
    body.detail !== "platform_access_denied"
  )
    return false;
  window.dispatchEvent(new Event(platformAccessDenied));
  if (!isPlatformAccessStandalone()) window.location.replace(platformPath("platform-access-denied"));
  return true;
}

export async function handlePlatformAccessResponse(response: Response): Promise<void> {
  if (response.status !== 403) return;
  try {
    handlePlatformAccessDenial(response.status, await response.clone().json());
  } catch {
    // A non-JSON denial belongs to the request's normal error handling.
  }
}
