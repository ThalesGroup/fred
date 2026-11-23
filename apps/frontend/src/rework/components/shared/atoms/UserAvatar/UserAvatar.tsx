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
import { getInitials } from "../../../../../utils/getInitials.ts";
import { useGetUserAvatarQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./UserAvatar.module.scss";

export interface UserAvatarProps {
  name: string;
  size: "x-small" | "small" | "medium" | "large";
  /** Profile picture; initials are shown without it or when it fails to load. */
  imageUrl?: string | null;
  /** Resolve a profile through an authorized shared space; RTK deduplicates readers. */
  subject?: { spaceId: string; userId: string };
}

const PIXEL_SIZE: Record<UserAvatarProps["size"], number> = {
  "x-small": 24,
  small: 32,
  medium: 40,
  large: 56,
};

export default function UserAvatar({ subject, ...props }: UserAvatarProps) {
  return subject ? <ScopedAvatar {...props} subject={subject} /> : <AvatarImage {...props} />;
}

function ScopedAvatar({ subject, ...props }: UserAvatarProps & { subject: NonNullable<UserAvatarProps["subject"]> }) {
  const { currentData, isError } = useGetUserAvatarQuery(subject, { refetchOnMountOrArgChange: 60 });
  return <AvatarImage {...props} imageUrl={isError ? undefined : currentData} />;
}

function AvatarImage({ name, size, imageUrl, ...props }: UserAvatarProps) {
  // Remembering the failed URL (not a flag) resets the fallback when the URL changes.
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const showImage = Boolean(imageUrl) && imageUrl !== failedUrl;

  return (
    <div className={styles["user-avatar"]} data-size={size} {...props}>
      {showImage ? (
        <img
          className={styles["user-avatar-image"]}
          src={imageUrl!}
          alt=""
          width={PIXEL_SIZE[size]}
          height={PIXEL_SIZE[size]}
          decoding="async"
          onError={() => setFailedUrl(imageUrl ?? null)}
        />
      ) : (
        getInitials(name)
      )}
    </div>
  );
}
