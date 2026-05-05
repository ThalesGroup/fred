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
}

export default function AvatarGroup({ avatars }: AvatarGroupProps) {
  return (
    <div className={styles.userAvatarContainer}>
      {avatars.length > 4 && <UserAvatar name={`+ ${(avatars.length - 4).toString()}`} size={"small"} />}
      {avatars.slice(0, 4).map((avatar, index) => (
        <Tooltip key={index} text={avatar.name}>
          <UserAvatar size={"small"} {...avatar} />
        </Tooltip>
      ))}
    </div>
  );
}
