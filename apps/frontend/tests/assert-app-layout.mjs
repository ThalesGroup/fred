// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { expect } from "@playwright/test";

// Check browser geometry, not just presence: a collapsed shell leaves every
// navigation item visible while moving the account trigger to the top.
export async function assertAccountAtBottom(page) {
  const account = page.getByRole("button", { name: /'s account$/ });
  await expect(account).toBeVisible();
  await expect
    .poll(async () => {
      const box = await account.boundingBox();
      return box ? page.viewportSize().height - box.y - box.height : -1;
    })
    .toBeGreaterThanOrEqual(0);
  await expect
    .poll(async () => {
      const box = await account.boundingBox();
      return box ? page.viewportSize().height - box.y - box.height : Infinity;
    })
    .toBeLessThanOrEqual(24);
}
