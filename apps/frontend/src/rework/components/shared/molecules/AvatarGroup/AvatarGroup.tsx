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

import styles from "./AvatarGroup.module.scss";
import UserAvatar, { UserAvatarProps } from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";

interface AvatarGroupProps {
  avatars: Omit<UserAvatarProps, "size">[];
  /** How many avatars render before the rest collapse into a "+N" badge.
   *  Lower it where the row shares a narrow line with something else - a
   *  TeamCard footer holding a join button has ~118px for the whole row. */
  max?: number;
  /** How many people the row stands for when `avatars` is a bounded sample;
   *  the badge then counts the undescribed ones too. Defaults to `avatars.length`. */
  total?: number;
}

export default function AvatarGroup({ avatars, max = 4, total = avatars.length }: AvatarGroupProps) {
  const hidden = avatars.slice(max);
  const extra = total - Math.min(avatars.length, max);
  return (
    <div className={styles.userAvatarContainer}>
      {extra > 0 && (
        // Wrapped like every other avatar, not bare: the container puts its
        // 2px ring on the direct child, and under the global border-box a
        // bare badge pays for that ring out of its own 2rem - it rendered 4px
        // smaller. The wrapper also earns it the list of hidden names.
        <Tooltip
          content={
            hidden.length > 0 && (
              <ul className={styles.hiddenAvatarNames}>
                {hidden.map((avatar, index) => (
                  <li key={index}>{avatar.name}</li>
                ))}
              </ul>
            )
          }
        >
          <UserAvatar name={`+ ${extra.toString()}`} size={"small"} />
        </Tooltip>
      )}
      {avatars.slice(0, max).map((avatar, index) => (
        <Tooltip key={index} text={avatar.name}>
          <UserAvatar size={"small"} {...avatar} />
        </Tooltip>
      ))}
    </div>
  );
}
