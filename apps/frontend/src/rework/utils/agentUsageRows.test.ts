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

import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";
import { agentUsageRows, CREATION_ASSISTANT_LABEL } from "./agentUsageRows";

const t = ((key: string) => `t:${key}`) as unknown as TFunction;

describe("agentUsageRows", () => {
  it("translates the creation assistant bucket and keeps agent names", () => {
    const rows = agentUsageRows(
      [
        { label: "Buyer assistant", value: 900 },
        { label: CREATION_ASSISTANT_LABEL, value: 200, kwh: 0.1 },
      ],
      t,
    );
    expect(rows).toEqual([
      { label: "Buyer assistant", value: 900 },
      { label: "t:rework.analytics.tokenUsage.byAgent.creationAssistant", value: 200, kwh: 0.1 },
    ]);
  });

  it("accepts missing data", () => {
    expect(agentUsageRows(undefined, t)).toEqual([]);
  });
});
