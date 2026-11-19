// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

/** The working organization's own pages: Home, and its content under `/team/<organizationId>`. */
export function isOrganizationRoute(pathname: string, organizationId: string | undefined): boolean {
  if (/^\/home(\/|$)/.test(pathname)) return true;
  return !!organizationId && /^\/team\/([^/]+)/.exec(pathname)?.[1] === organizationId;
}

/** Settings and usage swap a space's panel into its settings menu. */
export const isSpaceSettingsRoute = (pathname: string) => /^\/team\/[^/]+\/(settings|usage)(\/|$)/.test(pathname);
