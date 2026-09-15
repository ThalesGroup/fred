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

import type { ReactNode } from "react";
import TeamAdminCharterPage from "@components/pages/TeamAdminCharterPage/TeamAdminCharterPage.tsx";
import { useSelectedTeam } from "../../../../../hooks/useSelectedTeam.ts";

/** Shows the team administrator charter instead of a team's pages while the user is a
 *  pending admin of that team. The home page and the personal space never are. */
export default function TeamAdminCharterGate({ children }: { children: ReactNode }) {
  const { selectedTeam } = useSelectedTeam();
  const pending =
    !!selectedTeam &&
    "my_relations" in selectedTeam &&
    (selectedTeam.my_relations ?? []).includes("pending_team_admin");
  return pending ? <TeamAdminCharterPage /> : <>{children}</>;
}
