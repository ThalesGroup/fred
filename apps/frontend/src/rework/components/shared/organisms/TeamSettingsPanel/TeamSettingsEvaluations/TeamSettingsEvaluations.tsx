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

// Team-scoped evaluations, hosted inside the Team Settings modal. Because a modal
// cannot host sub-routes, the list / create / detail screens are switched via local
// view state instead of router navigation.

import { useState } from "react";
import { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import EvaluationCampaigns from "./views/EvaluationCampaigns";
import EvaluationCampaignCreate from "./views/EvaluationCampaignCreate";
import EvaluationCampaignDetail from "./views/EvaluationCampaignDetail";

type EvalView = { kind: "list" } | { kind: "create" } | { kind: "detail"; campaignId: string; selectedCaseId?: string };

interface TeamSettingsEvaluationsProps {
  team: TeamWithPermissions;
}

export default function TeamSettingsEvaluations({ team }: TeamSettingsEvaluationsProps) {
  const [view, setView] = useState<EvalView>({ kind: "list" });

  if (view.kind === "create") {
    return (
      <EvaluationCampaignCreate
        teamId={team.id}
        onCancel={() => setView({ kind: "list" })}
        onCreated={(campaignId) => setView({ kind: "detail", campaignId })}
      />
    );
  }

  if (view.kind === "detail") {
    return (
      <EvaluationCampaignDetail
        campaignId={view.campaignId}
        selectedCaseId={view.selectedCaseId}
        onBack={() => setView({ kind: "list" })}
      />
    );
  }

  return (
    <EvaluationCampaigns
      teamId={team.id}
      onNewCampaign={() => setView({ kind: "create" })}
      onOpenCampaign={(campaignId, selectedCaseId) => setView({ kind: "detail", campaignId, selectedCaseId })}
    />
  );
}
