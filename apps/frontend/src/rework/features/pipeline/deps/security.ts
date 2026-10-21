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

import { useMemo } from "react";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { HeaderMap, SecurityDeps } from "../scenarios/securityScenario";
import type { KnowledgeDeps } from "../scenarios/knowledgeScenario";

const LOCAL = /^(localhost|127\.|\[::1\])/;

export function useSecurityDeps(knowledge: KnowledgeDeps): SecurityDeps {
  return useMemo(
    () => ({
      origin: { https: window.location.protocol === "https:", local: LOCAL.test(window.location.hostname) },
      // Headers and raw error bodies are beyond what the generated client exposes.
      headersOf: async (path, token) => {
        const response = await fetch(path, {
          credentials: "omit",
          cache: "no-store",
          redirect: "manual",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        const headers: HeaderMap = {};
        response.headers.forEach((value, key) => {
          headers[key.toLowerCase()] = value;
        });
        const body = response.status >= 400 ? (await response.text()).slice(0, 4000) : "";
        if (response.status < 400) await response.body?.cancel();
        return { status: response.status, headers, body };
      },
      token: async () => ((await KeyCloakService.ensureFreshToken(30)) ? KeyCloakService.GetToken() : null),
      createLibrary: knowledge.createLibrary,
      deleteLibrary: knowledge.deleteLibrary,
      ingest: async (libraryId, file) => {
        await knowledge.ingestDocument(libraryId, file, new AbortController().signal);
        const doc = (await knowledge.documentsIn(libraryId)).find((d) => d.name === file.name);
        if (!doc) throw new Error("the document is not listed after ingestion");
        return doc.uid;
      },
    }),
    [knowledge],
  );
}
