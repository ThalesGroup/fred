// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

export const isPromptPublicationRoute = (pathname: string) =>
  /^\/team\/[^/]+\/prompts\/?$/.test(pathname) || /^\/(?:marketplace\/prompts|home)\/?$/.test(pathname);

/** These pages use Weaver admission, never Swift bootstrap/charter gates. */
export const isWeaverContentRoute = (pathname: string) =>
  /^\/team\/[^/]+(?:\/(?:agents|skills|settings(?:\/[^/]+)?|managed-chat\/[^/]+))?\/?$/.test(pathname) ||
  isPromptPublicationRoute(pathname);
