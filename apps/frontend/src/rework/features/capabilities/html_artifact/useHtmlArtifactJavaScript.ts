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

import { useSelectedTeam } from "../../../../hooks/useSelectedTeam";
import { useTeamCapabilitySettingsQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";

export const HTML_ARTIFACT_CAPABILITY_ID = "html_artifact";

/**
 * Whether this team may run script in an artifact, resolved at DISPLAY time.
 *
 * Deliberately not read from the stored artifact: the value is a posture an
 * administrator can withdraw, and a flag frozen when the page was produced would
 * leave every earlier interactive artifact running after the withdrawal. Asking
 * per mount is what makes a revocation reach content that already exists.
 *
 * Fails CLOSED — loading, error, and no team all answer `false`. A page that
 * briefly renders inert and then becomes interactive is a cosmetic flicker; the
 * reverse would run script the team may not run.
 */
export function useHtmlArtifactJavaScriptAllowed(): boolean {
  const { teamId } = useSelectedTeam();
  const { data } = useTeamCapabilitySettingsQuery(
    { teamId: teamId ?? "", capabilityId: HTML_ARTIFACT_CAPABILITY_ID },
    {
      skip: !teamId,
      // The posture must be re-resolved whenever the viewer opens, or a
      // revocation would sit behind a cache until a full reload.
      refetchOnMountOrArgChange: true,
    },
  );

  return data?.settings?.allow_javascript === true;
}
