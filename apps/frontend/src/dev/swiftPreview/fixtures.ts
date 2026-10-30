// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type { FetchArgs, FetchBaseQueryError } from "@reduxjs/toolkit/query";
import type {
  DocumentMetadata,
  StoreAuditReport,
  StoreAuditFixResponse,
  TagWithItemsId,
  TaskSummary,
} from "../../slices/legacyKnowledgeFlow/knowledgeFlowOpenApi";
import type {
  KnowledgeBaseDefinitionChoice,
  KnowledgeBaseInstanceSummary,
  PlatformStats,
} from "../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

const timestamp = "2026-10-30T09:00:00Z";
const documents: DocumentMetadata[] = [
  {
    identity: { document_uid: "preview-document", document_name: "Guide fictif.pdf" },
    source: { source_type: "push", retrievable: true, date_added_to_kb: timestamp },
    file: { file_type: "pdf", file_size_bytes: 2048 },
    tags: { tag_ids: ["preview-library"] },
    labels: ["Exemple"],
    processing: { stages: { raw: "done", preview: "done", vector: "done" } },
  },
  {
    identity: { document_uid: "preview-failed-document", document_name: "Extraction en erreur.pdf" },
    source: { source_type: "push", retrievable: false, date_added_to_kb: timestamp },
    file: { file_type: "pdf", file_size_bytes: 1024 },
    tags: { tag_ids: ["preview-library"] },
    processing: {
      stages: { raw: "done", preview: "failed" },
      errors: { preview: "Échec fictif pour examiner la présentation de l’erreur." },
    },
  },
];
const tags: TagWithItemsId[] = [
  {
    id: "preview-library",
    created_at: timestamp,
    updated_at: timestamp,
    owner_id: "preview-team",
    name: "Dossier fictif",
    path: "",
    type: "document",
    item_ids: documents.map((d) => d.identity.document_uid),
  },
];
const tasks: TaskSummary[] = ["pending", "running", "failed", "succeeded"].map((state, index) => ({
  task_id: `preview-task-${index}`,
  kind: "ingestion",
  state: state as TaskSummary["state"],
  progress: index === 1 ? 0.5 : undefined,
  target: { type: "document", id: "preview-document", label: `Import fictif ${index + 1}` },
  created_at: timestamp,
  updated_at: timestamp,
  error: state === "failed" ? "Erreur simulée : document illisible" : undefined,
}));
let audit: StoreAuditReport = {
  has_anomalies: true,
  total_seen: 2,
  metadata_count: 2,
  vector_count: 1,
  content_count: 2,
  anomalies: [
    {
      document_uid: "preview-failed-document",
      document_name: "Extraction en erreur.pdf",
      present_in_metadata: true,
      present_in_content_store: true,
      present_in_vector_store: false,
      vector_chunks: 0,
      issues: ["missing_vectors"],
    },
  ],
};
const definitions: KnowledgeBaseDefinitionChoice[] = [
  { definition_id: "preview-source", name: "Source fictive", description: "Exemple local sans connexion à un dépôt." },
];
const bases: KnowledgeBaseInstanceSummary[] = [
  {
    id: "preview-kb",
    definition_id: "preview-source",
    definition_name: "Source fictive",
    team_id: "preview-team",
    library_id: "preview-library",
    library_name: "Bibliothèque fictive",
    schedule: { type: "interval", every_seconds: 3600 },
    suspended: false,
    configuration: {},
    created_at: timestamp,
    updated_at: timestamp,
  },
];
const stats: PlatformStats = {
  teams: 1,
  distinct_users: 3,
  total_agents: 2,
  total_prompts: 4,
  per_team: [
    {
      team_id: "preview-team",
      name: "Équipe fictive",
      admins: 1,
      editors: 1,
      analysts: 0,
      members: 1,
      total_members: 3,
      agents: 2,
      prompts: 4,
    },
  ],
};

type Result = { data: unknown; error?: never } | { error: FetchBaseQueryError; data?: never };
/** Explicit allowlist: no fallback HTTP and no invented successful response. State is reset on reload. */
export function previewQuery(args: string | FetchArgs): Result {
  const request = typeof args === "string" ? { url: args } : args;
  const path = new URL(request.url, "http://swift-preview.invalid").pathname;
  const method = request.method ?? "GET";
  const body = request.body ?? {};
  const read = method === "GET";
  const data = (value: unknown): Result => ({ data: structuredClone(value) });
  if (read && path === "/config.json") return data({ properties: {}, feature_flags: {} });
  if (read && path === "/control-plane/v1/frontend/config")
    return data({ user_auth: { enabled: false }, root_bootstrap_required: false });
  if (read && path === "/theme-properties.json") return data({});
  if (read && path === "/theme-catalog.json") return data({ themes: [] });
  if (read && path === "/knowledge-flow/v1/documents/audit") return data(audit);
  if (method === "POST" && path === "/knowledge-flow/v1/documents/audit/fix") {
    const before = structuredClone(audit);
    audit = { ...audit, has_anomalies: false, anomalies: [] };
    return data({ before, after: audit, reset_metadata: ["preview-failed-document"] } satisfies StoreAuditFixResponse);
  }
  if (read && path === "/knowledge-flow/v1/tasks") return data({ tasks });
  if (read && path === "/control-plane/v1/tasks") return data({ tasks: [] });
  const ack = path.match(/^\/knowledge-flow\/v1\/tasks\/(preview-task-\d+)\/ack$/);
  if (method === "POST" && ack) {
    const task = tasks.find((item) => item.task_id === ack[1]);
    if (task) {
      task.acknowledged_at = timestamp;
      return data({ task_id: task.task_id, acknowledged_at: timestamp, acknowledged_by: "preview-user" });
    }
  }
  if (read && path === "/control-plane/v1/import-export/stats") return data(stats);
  if (read && path === "/control-plane/v1/knowledge-bases/definitions") return data(definitions);
  if (read && path === "/control-plane/v1/knowledge-bases/definitions/preview-source/fields")
    return data({ configuration_fields: [] });
  if (read && path === "/control-plane/v1/knowledge-bases/instances") return data(bases);
  if (read && path === "/control-plane/v1/knowledge-bases/instances/preview-kb") return data(bases[0]);
  if (read && path === "/control-plane/v1/teams/preview-team")
    return data({
      id: "preview-team",
      name: "Équipe fictive",
      permissions: ["can_read", "can_update_resources", "can_use_team_knowledge_bases"],
      my_relations: ["team_editor"],
    });
  if (read && path === "/knowledge-flow/v1/tags") return data(tags);
  if (read && path === "/knowledge-flow/v1/tags/preview-library") return data(tags[0]);
  if (method === "POST" && path === "/knowledge-flow/v1/documents/metadata/browse")
    return data({ documents, total: documents.length });
  if (method === "POST" && path === "/knowledge-flow/v1/documents/metadata/search") return data(documents);
  if (method === "POST" && path === "/knowledge-flow/v1/documents/metadata/tag-sizes")
    return data({ sizes: { "preview-library": 3072 } });
  if (read && path === "/knowledge-flow/v1/tags/stats")
    return data({ total_documents: 2, total_bytes: 3072, entries: [{ bucket: "pdf", count: 2, size_bytes: 3072 }] });
  if (read && path === "/knowledge-flow/v1/documents/labels") return data(["Exemple", "À relire"]);
  const documentPath = path.match(
    /^\/knowledge-flow\/v1\/(?:document\/metadata|documents)\/(preview-(?:failed-)?document)\/(name|labels)$/,
  );
  if (documentPath) {
    const document = documents.find((item) => item.identity.document_uid === documentPath[1]);
    if (document && method === "PUT" && documentPath[2] === "name") {
      document.identity.document_name = body.name;
      return data(document);
    }
    if (document && method === "PATCH" && documentPath[2] === "labels") {
      document.labels = [
        ...new Set([
          ...(document.labels ?? []).filter((label) => !(body.remove ?? []).includes(label)),
          ...(body.add ?? []),
        ]),
      ];
      return data(document.labels);
    }
  }
  return {
    error: {
      status: 501,
      data: { detail: `Aperçu Swift : interaction non simulée (${method} ${path}). Aucun appel backend effectué.` },
    },
  };
}

/** Installed only in the separate preview window, before importing any UI or API module. */
export const previewFetch: typeof fetch = async (input, init) => {
  const request =
    input instanceof Request
      ? new Request(input, init)
      : new Request(new URL(String(input), window.location.origin), init);
  let body: unknown;
  if (
    request.method !== "GET" &&
    request.method !== "HEAD" &&
    request.headers.get("content-type")?.includes("application/json")
  )
    body = await request.json();
  const result = previewQuery({ url: request.url, method: request.method, body });
  return Response.json(result.error ? result.error.data : result.data, { status: result.error ? 501 : 200 });
};
