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

// Renderers for the frozen base `UiPart` kinds (link, geo).
// Capability kinds come from plugins.

import type { LinkPart } from "../../../slices/runtime/runtimeOpenApi";
import { ArtifactLinkChip } from "@shared/molecules/ArtifactLinks/ArtifactLinkChip";
import { CitationLinkChip } from "@shared/molecules/ArtifactLinks/CitationLinkChip";
import type { UiPartIdentity, UiPartRenderer, UiPartRendererProps } from "./types";
import { GeoPartRenderer } from "./geo/GeoPartRenderer";

// Citations open the third-party page directly; every other kind is a Fred file.
function LinkPartRenderer({ part }: UiPartRendererProps) {
  const link = part as unknown as LinkPart;
  return link.kind === "citation" ? <CitationLinkChip link={link} /> : <ArtifactLinkChip link={link} />;
}

/**
 * A download chip is about its file: the same href twice in a message is one chip.
 * Other links, citations first, may legitimately repeat an href and are never merged.
 */
export const builtinPartIdentities: Record<string, UiPartIdentity> = {
  link: (part) => (part.kind === "download" && typeof part.href === "string" ? part.href : undefined),
};

/** Registry seed for the frozen base kinds; plugin kinds must not collide. */
export const builtinPartRenderers: Record<string, UiPartRenderer> = {
  link: LinkPartRenderer,
  geo: GeoPartRenderer,
};
