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

import type { TagNode as LegacyTagNode } from "../../../../../shared/utils/tagTree.ts";
import type { Folder } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

// Presentation nodes retain the original renderer. Manager metadata is never a KF tag:
// no tag id is synthesized and document operations cannot consume these nodes.
export type TagNode = LegacyTagNode & { managerFolder?: Folder };

export const folderNode = (folder: Folder): TagNode => ({
  name: folder.name,
  full: folder.id,
  children: new Map(),
  tagsHere: [],
  managerFolder: folder,
});
