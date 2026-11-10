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
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { usePromptsDeps } from "../../../../features/pipeline/deps/prompts";
import { useSelfTestFamilies } from "../../../../features/pipeline/families";
import { promptsScenario } from "../../../../features/pipeline/scenarios/promptsScenario";
import { useScenarioRun } from "../../../../features/pipeline/useScenarioRun";
import { AuthorizationExtras } from "./AuthorizationExtras";
import { PromptSpaceSelect } from "./PromptSpaceSelect";
import { SelfTestView } from "./SelfTestView";

export default function SelfTestPage() {
  const [promptSpaceId, setPromptSpaceId] = useState<string>();
  const families = useSelfTestFamilies(promptSpaceId);
  return (
    <SelfTestView
      families={families}
      promptSetup={(busy) => <PromptSpaceSelect value={promptSpaceId} onChange={setPromptSpaceId} disabled={busy} />}
      manual={(props) => <AuthorizationExtras {...props} />}
    />
  );
}

export function PromptsSelfTestPage() {
  const access = useManagerPlatformAdmin();
  const { t } = useTranslation();
  const [promptSpaceId, setPromptSpaceId] = useState<string>();
  const run = useScenarioRun(promptsScenario, usePromptsDeps(promptSpaceId));
  if (access.isLoading || (access.isFetching && !access.currentData)) return null;
  if (access.isError) return <ServiceNotice icon="info" title={t("rework.manager.unavailable")} />;
  if (!access.isAdmin) return <Navigate to="/unauthorized" replace />;
  return (
    <SelfTestView
      families={[{ id: "prompts", icon: "notes", run }]}
      promptSetup={(busy) => <PromptSpaceSelect value={promptSpaceId} onChange={setPromptSpaceId} disabled={busy} />}
    />
  );
}
