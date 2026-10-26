// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

export const isAgentManagementRoute = (pathname: string) => /^\/team\/[^/]+\/agents\/?$/.test(pathname);
