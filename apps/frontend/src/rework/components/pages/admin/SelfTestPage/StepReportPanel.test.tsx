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

// The verdict this panel puts on a whole run. Only the summary badge renders a
// label, so the echoed `rework.tasks.state.*` key is the overall verdict under
// test; the per-step badges are icon-only.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { StepReport, StepStatus } from "../../../../features/pipeline/types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

import { StepReportPanel } from "./StepReportPanel";

function step(id: string, status: StepStatus, optional = false): StepReport {
  return { id, title: id, status, optional };
}

function verdictOf(steps: StepReport[]): string {
  const html = renderToStaticMarkup(<StepReportPanel steps={steps} isRunning={false} emptyLabel="empty" />);
  const match = html.match(/rework\.tasks\.state\.(\w+)</);
  return match?.[1] ?? "none";
}

describe("StepReportPanel verdict", () => {
  it("reads a run that skipped out before validating anything as cancelled", () => {
    // A realm without the probe client: nothing failed, nothing was proven.
    expect(verdictOf([step("probe-availability", "skipped"), step("delete-agent", "skipped", true)])).toBe("cancelled");
  });

  it("still reads a required step skipped mid-run as failed", () => {
    expect(verdictOf([step("create-folder", "passed"), step("expiry-turn", "skipped")])).toBe("failed");
  });

  it("keeps a clean run with optional teardown skips a success", () => {
    expect(verdictOf([step("create-folder", "passed"), step("delete-folder", "skipped", true)])).toBe("succeeded");
  });

  it("reads any failure as failed, whatever else the run did", () => {
    expect(verdictOf([step("probe-availability", "failed"), step("delete-agent", "skipped", true)])).toBe("failed");
    expect(verdictOf([step("create-folder", "passed"), step("expiry-turn", "failed")])).toBe("failed");
  });
});
