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
// cannot host sub-routes, the screens are switched via local view state instead of
// router navigation.
//
// The screens follow the two nouns of RFC AGENT-EVALUATION §8.5: an Evaluation (a
// versioned, reusable case set) holds N Runs (one execution each, against a target
// chosen at start time). Creating an Evaluation never starts a Run.
//
//   evaluations ──▶ evaluationCreate
//        │
//        └──▶ runs (of one evaluation) ──▶ runCreate
//                     │
//                     └──▶ runDetail

import { useState } from "react";
import { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import Evaluations from "./views/Evaluations";
import EvaluationCreate from "./views/EvaluationCreate";
import EvaluationRuns from "./views/EvaluationRuns";
import RunCreate from "./views/RunCreate";
import EvaluationRunDetail from "./views/EvaluationRunDetail";

type EvalView =
  | { kind: "evaluations" }
  | { kind: "evaluationCreate" }
  | { kind: "runs"; evaluationId: string; evaluationName: string }
  | { kind: "runCreate"; evaluationId: string; evaluationName: string }
  | { kind: "runDetail"; evaluationId: string; evaluationName: string; runId: string; selectedCaseId?: string };

interface TeamSettingsEvaluationsProps {
  team: TeamWithPermissions;
}

export default function TeamSettingsEvaluations({ team }: TeamSettingsEvaluationsProps) {
  const [view, setView] = useState<EvalView>({ kind: "evaluations" });

  if (view.kind === "evaluationCreate") {
    return (
      <EvaluationCreate
        teamId={team.id}
        onCancel={() => setView({ kind: "evaluations" })}
        // Back to the full list, not straight into the new evaluation's runs —
        // seeing it land in the list first reinforces that a run is started
        // FROM an evaluation, a deliberate next click, not an automatic step.
        onCreated={() => setView({ kind: "evaluations" })}
      />
    );
  }

  if (view.kind === "runCreate") {
    return (
      <RunCreate
        teamId={team.id}
        evaluationId={view.evaluationId}
        evaluationName={view.evaluationName}
        onCancel={() => setView({ kind: "runs", evaluationId: view.evaluationId, evaluationName: view.evaluationName })}
        onStarted={(runId) =>
          setView({
            kind: "runDetail",
            evaluationId: view.evaluationId,
            evaluationName: view.evaluationName,
            runId,
          })
        }
      />
    );
  }

  if (view.kind === "runDetail") {
    return (
      <EvaluationRunDetail
        runId={view.runId}
        selectedCaseId={view.selectedCaseId}
        teamId={team.id}
        evaluationName={view.evaluationName}
        onBack={() => setView({ kind: "runs", evaluationId: view.evaluationId, evaluationName: view.evaluationName })}
        onBackToList={() => setView({ kind: "evaluations" })}
      />
    );
  }

  if (view.kind === "runs") {
    return (
      <EvaluationRuns
        evaluationId={view.evaluationId}
        evaluationName={view.evaluationName}
        teamId={team.id}
        onBack={() => setView({ kind: "evaluations" })}
        onNewRun={() =>
          setView({ kind: "runCreate", evaluationId: view.evaluationId, evaluationName: view.evaluationName })
        }
        onOpenRun={(runId, selectedCaseId) =>
          setView({
            kind: "runDetail",
            evaluationId: view.evaluationId,
            evaluationName: view.evaluationName,
            runId,
            selectedCaseId,
          })
        }
      />
    );
  }

  return (
    <Evaluations
      teamId={team.id}
      onNewEvaluation={() => setView({ kind: "evaluationCreate" })}
      onOpenEvaluation={(evaluationId, evaluationName) => setView({ kind: "runs", evaluationId, evaluationName })}
    />
  );
}
