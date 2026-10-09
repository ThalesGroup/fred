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

import { useTranslation } from "react-i18next";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import SelectableCard from "@shared/molecules/SelectableCard/SelectableCard";
import type { MaterialIconType } from "@shared/utils/Type";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AnnouncementKindChooser.module.css";

type AnnouncementKind = NonNullable<Announcement["kind"]>;

const KINDS: { kind: AnnouncementKind; icon: MaterialIconType; descriptionKey: string }[] = [
  { kind: "banner", icon: "campaign", descriptionKey: "bannerDescription" },
  { kind: "patch_note", icon: "new_releases", descriptionKey: "patchNoteDescription" },
];

interface AnnouncementKindChooserProps {
  open: boolean;
  onChoose: (kind: AnnouncementKind) => void;
  onCancel: () => void;
}

/** "New announcement" first asks which type. A tile opens its editor at once:
 *  the choice is the whole question, so a confirm step would only add a click. */
export default function AnnouncementKindChooser({ open, onChoose, onCancel }: AnnouncementKindChooserProps) {
  const { t } = useTranslation();
  return (
    // The tiles are the choice; Cancel, in its usual style, is the only action.
    <Dialog
      open={open}
      title={t("rework.announcements.chooser.title")}
      confirmLabel=""
      onConfirm={onCancel}
      onCancel={onCancel}
      hideConfirm
      maxWidth={560}
    >
      <div className={styles.tiles}>
        {KINDS.map(({ kind, icon, descriptionKey }) => (
          <SelectableCard
            key={kind}
            icon={icon}
            title={t(`rework.announcements.kind.${kind}`)}
            description={t(`rework.announcements.chooser.${descriptionKey}`)}
            onSelect={() => onChoose(kind)}
          />
        ))}
      </div>
    </Dialog>
  );
}
