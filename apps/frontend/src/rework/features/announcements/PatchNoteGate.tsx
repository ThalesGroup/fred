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

// Opens the announced patch notes when an announcement is pending for this user at
// app load, and records it as seen on close. Mounted inside GcuGuard/BootstrapGuard
// (see App.tsx), above the router, so it never remounts on navigation.

import { useState } from "react";
import { PatchNoteDialog, type PatchNote } from "@shared/molecules/PatchNoteDialog/PatchNoteDialog";
import { useMarkPatchNoteAnnouncementSeenMutation } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { usePatchNoteHistory } from "./usePatchNoteHistory";

export default function PatchNoteGate() {
  const { notes, pendingAnnouncementId, loaded } = usePatchNoteHistory();
  const [markSeen] = useMarkPatchNoteAnnouncementSeenMutation();
  // Decided on the first read only: an announcement made later in this page
  // view waits for the next load, as it does for every other user.
  // The notes are kept with their id: a later refetch must not change what
  // is shown under the id that gets recorded.
  const [atLoad, setAtLoad] = useState<{ pendingId: string | null; notes: PatchNote[] }>();
  const [closed, setClosed] = useState(false);
  if (loaded && atLoad === undefined) setAtLoad({ pendingId: pendingAnnouncementId, notes });

  const pendingAtLoad = atLoad?.pendingId;
  if (!pendingAtLoad || closed || atLoad.notes.length === 0) return null;

  const onClose = () => {
    // Closed for this page view whatever the write does; a failed one only
    // means the dialog may open again at a later load.
    setClosed(true);
    void markSeen({ announcementId: pendingAtLoad });
  };

  return <PatchNoteDialog open notes={atLoad.notes} onClose={onClose} />;
}
