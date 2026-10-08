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

import { useEffect, useState } from "react";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam";
import {
  useLazyTeamCapabilitySettingsQuery,
  useTeamCapabilitySettingsQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";

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
export function useHtmlArtifactJavaScriptAllowed(displayKey = ""): boolean {
  const { teamId } = useSelectedTeam();
  const { currentData, isFetching, isError, refetch } = useTeamCapabilitySettingsQuery(
    { teamId: teamId ?? "", capabilityId: HTML_ARTIFACT_CAPABILITY_ID },
    {
      skip: !teamId,
      // The posture must be re-resolved whenever the viewer opens, or a
      // revocation would sit behind a cache until a full reload.
      refetchOnMountOrArgChange: true,
    },
  );

  // A card can stay mounted while an administrator changes the posture. When
  // the pane selects a new artifact, demand a fresh read before displaying it.
  const [verifiedDisplay, setVerifiedDisplay] = useState<string | null>(null);
  const identity = `${teamId ?? ""}:${displayKey}`;
  const [renderedIdentity, setRenderedIdentity] = useState(identity);
  if (renderedIdentity !== identity) {
    // Reset during render, before React can commit a frame using an old grant.
    // An effect would be too late when a closed artifact is reopened.
    setRenderedIdentity(identity);
    setVerifiedDisplay(null);
  }
  useEffect(() => {
    if (!teamId || !displayKey) return;
    let active = true;
    void refetch()
      .unwrap()
      .then((result) => {
        if (active) setVerifiedDisplay(result.settings?.allow_javascript === true ? identity : null);
      })
      .catch(() => {
        // A failed refresh leaves the current display unverified.
      });
    return () => {
      active = false;
    };
  }, [teamId, displayKey, identity, refetch]);

  // `data` can belong to the previous team, and a cached success can survive a
  // failed refetch. Neither is evidence of the current team's right.
  return Boolean(
    teamId &&
      !isFetching &&
      !isError &&
      currentData?.settings?.allow_javascript === true &&
      (!displayKey || verifiedDisplay === identity),
  );
}

/** Recheck at an export/open action: a mounted chat card's cached grant is not enough. */
export function useCheckHtmlArtifactJavaScriptAllowed(): () => Promise<boolean> {
  const { teamId } = useSelectedTeam();
  const [read] = useLazyTeamCapabilitySettingsQuery();
  return async () => {
    if (!teamId) return false;
    try {
      const result = await read({ teamId, capabilityId: HTML_ARTIFACT_CAPABILITY_ID }, false).unwrap();
      return result.settings?.allow_javascript === true;
    } catch {
      return false;
    }
  };
}
