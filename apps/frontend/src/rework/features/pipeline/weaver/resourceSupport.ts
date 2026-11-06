// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { enhancedControlPlaneApi } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Receipt } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { FRESH } from "../deps/api";
import { runStep, SkipStep } from "../step";
import type { Reporter } from "../types";
import type { WeaverChecks } from "./checks";
import {
  runManagerImport,
  managerImportsSnapshot,
  dismissManagerImport,
  type ManagerDispatch,
  managerActor,
} from "../../imports/managerImportRun";

export const cp = enhancedControlPlaneApi.endpoints;

export function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

export function requireSpace(checks: WeaverChecks, signal: AbortSignal) {
  signal.throwIfAborted();
  if (!checks.spaceId) throw new SkipStep("Select an accessible business space before running this group.");
}

export async function requireWrite(checks: WeaverChecks, signal: AbortSignal) {
  requireSpace(checks, signal);
  const access = await checks
    .dispatch(cp.authorizeSpace.initiate({ spaceCheck: { space_id: checks.spaceId, permission: "write" } }))
    .unwrap();
  if (!access.allowed)
    throw new SkipStep("The selected space does not grant resource write access to the current person.");
}

export async function pause(signal: AbortSignal, milliseconds = 1000) {
  signal.throwIfAborted();
  await new Promise<void>((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(signal.reason ?? new Error("Run cancelled"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", abort, { once: true });
  });
}

export async function waitForDeletion(checks: WeaverChecks, receipt: Receipt) {
  const validate = (current: Receipt) => {
    assert(
      current.id === receipt.id &&
        current.target_id === receipt.target_id &&
        current.target_kind === receipt.target_kind &&
        current.target_parent_id === receipt.target_parent_id &&
        current.actor_subject === receipt.actor_subject &&
        current.organization_id === receipt.organization_id,
      "Deletion receipt identity changed.",
    );
    assert(
      ["queued", "running", "retrying", "blocked", "completed"].includes(current.status),
      "Deletion receipt state is invalid.",
    );
    assert(!current.error_code && current.status !== "blocked", "Resource deletion reported an error.");
  };
  validate(receipt);
  const dueAt = Date.parse(receipt.due_at);
  assert(Number.isFinite(dueAt), "Deletion receipt has no valid due date.");
  if (receipt.status === "completed") return { completed: true, receipt, detail: "Physical deletion completed." };
  if (dueAt > Date.now())
    return {
      completed: false,
      receipt,
      detail: "Logical retirement verified; physical deletion is scheduled by the retention policy.",
    };
  const deadline = Date.now() + 120_000;
  let current = receipt;
  while (current.status !== "completed" && Date.now() < deadline) {
    await pause(AbortSignal.timeout(Math.max(1, deadline - Date.now()) + 1000), Math.min(2000, deadline - Date.now()));
    current = await checks.dispatch(cp.deletionStatus.initiate({ operationId: receipt.id }, FRESH)).unwrap();
    validate(current);
  }
  return {
    completed: current.status === "completed",
    receipt: current,
    detail:
      current.status === "completed"
        ? "Physical deletion completed."
        : "Logical retirement verified; physical deletion remains scheduled after the bounded cleanup observation.",
  };
}

export async function registerTestConversation(checks: WeaverChecks, agentInstanceId: string, revision: number) {
  const sessionId = crypto.randomUUID();
  const saved = await checks
    .dispatch(
      cp.createSession.initiate({
        spaceId: checks.spaceId,
        createSessionRequest: {
          session_id: sessionId,
          agent_instance_id: agentInstanceId,
          agent_configuration_revision: revision,
          title: "Disposable conversation",
        },
      }),
    )
    .unwrap();
  assert(
    saved.session_id === sessionId && saved.space_id === checks.spaceId && saved.agent_instance_id === agentInstanceId,
    "Conversation registration changed its identity or space.",
  );
  return sessionId;
}

export async function deleteTestConversation(checks: WeaverChecks, sessionId: string) {
  const args = { spaceId: checks.spaceId, sessionId };
  const receipt = await checks.dispatch(cp.deleteSession.initiate({ ...args, immediate: true })).unwrap();
  assert(
    receipt.target_kind === "session" &&
      receipt.target_id === sessionId &&
      receipt.target_parent_id === checks.spaceId &&
      receipt.actor_subject === checks.userId,
    "The conversation deletion receipt does not match the disposable conversation.",
  );
  await expectAbsent(() => checks.dispatch(cp.getSession.initiate(args, FRESH)).unwrap());
  const list = await checks.dispatch(cp.listSessions.initiate({ spaceId: checks.spaceId }, FRESH)).unwrap();
  assert(!list.some((item) => item.session_id === sessionId), "Deleted conversation remains in the list.");
  const outcome = await waitForDeletion(checks, receipt);
  if (!outcome.completed) throw new Error(outcome.detail);
  return outcome.detail;
}

export async function folderListed(checks: WeaverChecks, folderId: string) {
  let offset = 0;
  for (let page = 0; page < 100; page++) {
    const directory = await checks
      .dispatch(cp.entries.initiate({ id: checks.spaceId, offset, limit: 200 }, FRESH))
      .unwrap();
    if (directory.items.some((entry) => entry.kind === "folder" && entry.data.id === folderId)) return true;
    offset += directory.items.length;
    if (offset >= directory.total) return false;
    assert(directory.items.length > 0, "Directory pagination stopped before the requested folder could be checked.");
  }
  throw new Error("Directory exceeds the bounded cleanup verification window.");
}

export async function expectAbsent(read: () => Promise<unknown>) {
  try {
    await read();
  } catch (error) {
    if ((error as { status?: unknown })?.status === 404) return;
    throw error;
  }
  throw new Error("Deleted resource is still readable.");
}

export async function requireCapabilities(checks: WeaverChecks, runtimeId: string, capabilityIds: string[]) {
  const policies = await checks
    .dispatch(cp.spaceCapabilityPolicies.initiate({ spaceId: checks.spaceId }, FRESH))
    .unwrap();
  const policy = policies.find((item) => item.runtime_id === runtimeId);
  const missing = capabilityIds.filter(
    (id) =>
      !policy?.reachable ||
      !policy.source_enabled ||
      !policy.offers.some((offer) => offer.capability_id === id && offer.permitted && offer.advertised),
  );
  if (missing.length) {
    const label = missing.includes("mcp-knowledge-flow-mcp-tabular")
      ? "tabular SQL"
      : missing.includes("document_access")
        ? "document access"
        : "requested";
    throw new SkipStep(`The required ${label} capability is not advertised and permitted in this space.`);
  }
}

export async function provisionDisposableAgent(
  checks: WeaverChecks,
  signal: AbortSignal,
  label: string,
  templateKey?: string,
  capabilityIds?: string[],
) {
  requireSpace(checks, signal);
  if (!["team", "project", "personal"].includes(checks.spaceKind ?? ""))
    throw new SkipStep(
      "Agent provisioning requires a team, project or personal space. Select one to run agent-dependent checks.",
    );
  await requireWrite(checks, signal);
  const templates = await checks.dispatch(cp.spaceAgentTemplates.initiate({ spaceId: checks.spaceId }, FRESH)).unwrap();
  const available = templates.filter((item) => item.team_instantiable && item.status === "available");
  const template = templateKey
    ? available.find((item) => item.source_agent_id === templateKey)
    : (available.find((item) => item.source_agent_id === "fred.github.test_assistant") ?? available[0]);
  if (!template) throw new SkipStep("No available, instantiable agent template is authorized in this space.");
  if (capabilityIds?.length) await requireCapabilities(checks, template.source_runtime_id, capabilityIds);
  signal.throwIfAborted();
  return checks
    .dispatch(
      cp.createAgentInstance.initiate({
        spaceId: checks.spaceId,
        createAgentInstanceRequest: {
          template_id: template.template_id,
          display_name: `Self-test ${label} ${crypto.randomUUID()}`,
          usage_statement: "Disposable self-test instance.",
          ...(capabilityIds ? { capability_ids: capabilityIds } : {}),
        },
      }),
    )
    .unwrap();
}

interface PendingFolder {
  actor: string;
  userId: string;
  spaceId: string;
  folderId: string;
  folderName: string;
  createdAt: string;
  uploadKey?: string;
  documentId?: string;
  deletionId?: string;
}

interface TabularFixtureInput {
  file: File | (() => Promise<File>);
  marker: string;
  tabular: true;
}
async function ownedFolder(checks: WeaverChecks, pending: PendingFolder) {
  assert(
    pending.actor === managerActor() &&
      pending.userId === checks.userId &&
      pending.spaceId === checks.spaceId &&
      pending.folderName.startsWith("Self-test ") &&
      !!pending.createdAt,
    "Disposable folder ownership cannot be verified.",
  );
  let offset = 0;
  for (let page = 0; page < 100; page++) {
    const directory = await checks
      .dispatch(cp.entries.initiate({ id: checks.spaceId, offset, limit: 200 }, FRESH))
      .unwrap();
    const found = directory.items.find((entry) => entry.kind === "folder" && entry.data.id === pending.folderId);
    if (found?.kind === "folder") {
      assert(
        found.data.space_id === checks.spaceId &&
          found.data.name === pending.folderName &&
          found.data.created_at === pending.createdAt,
        "The folder no longer matches its disposable creation receipt.",
      );
      return found.data;
    }
    offset += directory.items.length;
    if (offset >= directory.total) return null;
    assert(directory.items.length > 0, "Directory pagination stopped during ownership verification.");
  }
  throw new Error("Directory exceeds the bounded ownership verification window.");
}

async function cleanupFolder(checks: WeaverChecks, pending: PendingFolder) {
  const folder = await ownedFolder(checks, pending);
  if (!folder) {
    return;
  }
  if (!pending.documentId) {
    const candidates = managerImportsSnapshot().filter(
      (entry) => entry.folderId === folder.id && entry.spaceId === checks.spaceId,
    );
    assert(
      candidates.length <= 1,
      "Multiple import records reference the disposable folder; inspect it before cleanup.",
    );
    const key = pending.uploadKey ?? candidates[0]?.key;
    if (key) {
      const upload = await checks.dispatch(cp.receipt.initiate({ id: key }, FRESH)).unwrap();
      assert(
        upload.request_key === key && upload.space_id === checks.spaceId && upload.folder_id === folder.id,
        "The import receipt does not match the disposable folder.",
      );
      if (upload.status === "pending")
        throw new SkipStep("The upload is still pending; its disposable folder could not be cleaned up.");
      if (upload.status === "stored") {
        assert(upload.document_id, "The stored upload receipt has no document identity.");
        pending.documentId = upload.document_id;
        pending.uploadKey = key;
      }
    }
  }
  const contents = await checks
    .dispatch(cp.entries.initiate({ id: checks.spaceId, parentId: folder.id, limit: 200 }, FRESH))
    .unwrap();
  assert(
    contents.total <= 1 &&
      contents.items.every(
        (entry) =>
          entry.kind === "document" && entry.data.id === pending.documentId && entry.data.created_by === checks.userId,
      ),
    "The disposable folder contains unrecognized content; automatic removal is refused.",
  );
  if (pending.documentId) {
    const receipt = pending.deletionId
      ? await checks.dispatch(cp.deletionStatus.initiate({ operationId: pending.deletionId }, FRESH)).unwrap()
      : await checks.dispatch(cp.deleteDocument.initiate({ id: pending.documentId, immediate: true })).unwrap();
    assert(
      receipt.target_kind === "document" &&
        receipt.target_id === pending.documentId &&
        receipt.target_parent_id === checks.spaceId &&
        receipt.actor_subject === checks.userId &&
        receipt.organization_id === checks.organizationId,
      "The document deletion receipt does not match the disposable fixture.",
    );
    pending.deletionId = receipt.id;
    const retired = await checks
      .dispatch(cp.entries.initiate({ id: checks.spaceId, parentId: folder.id, limit: 200 }, FRESH))
      .unwrap();
    assert(
      !retired.items.some((entry) => entry.data.id === pending.documentId),
      "Deleted document remains in its folder.",
    );
    const outcome = await waitForDeletion(checks, receipt);
    if (!outcome.completed) throw new Error(`${outcome.detail} The disposable folder could not yet be removed.`);
  }
  const empty = await checks
    .dispatch(cp.entries.initiate({ id: checks.spaceId, parentId: folder.id, limit: 200 }, FRESH))
    .unwrap();
  assert(
    empty.total === 0 && empty.items.length === 0,
    "The disposable folder is not empty; recursive removal is refused.",
  );
  await ownedFolder(checks, pending);
  await checks.dispatch(cp.deleteFolder.initiate({ id: folder.id, emptyOnly: true })).unwrap();
  assert(!(await folderListed(checks, folder.id)), "Deleted folder remains in the directory.");
}

interface FixtureReporting {
  report: Reporter;
  id: string;
  title: string;
  detail?: string;
}
type KnowledgeFixture = Awaited<ReturnType<typeof createKnowledgeFixture>>;
export function ingestKnowledgeFixture(
  checks: WeaverChecks,
  signal: AbortSignal,
  input?: TabularFixtureInput,
): Promise<KnowledgeFixture>;
export function ingestKnowledgeFixture(
  checks: WeaverChecks,
  signal: AbortSignal,
  input: TabularFixtureInput | undefined,
  reporting: FixtureReporting,
): Promise<KnowledgeFixture | null>;
export async function ingestKnowledgeFixture(
  checks: WeaverChecks,
  signal: AbortSignal,
  input?: TabularFixtureInput,
  reporting?: FixtureReporting,
): Promise<KnowledgeFixture | null> {
  const create = async () => {
    await requireWrite(checks, signal);
    return createKnowledgeFixture(checks, signal, input);
  };
  if (!reporting) return create();
  return runStep(reporting.report, reporting.id, reporting.title, async () => ({
    value: await create(),
    detail: reporting.detail,
  }));
}

async function createKnowledgeFixture(checks: WeaverChecks, signal: AbortSignal, input?: TabularFixtureInput) {
  const inputFile = typeof input?.file === "function" ? await input.file() : input?.file;
  signal.throwIfAborted();
  const name = `Self-test ${crypto.randomUUID()}`;
  const folder = await checks
    .dispatch(cp.createFolder.initiate({ createFolder: { space_id: checks.spaceId, name } }))
    .unwrap();
  const pending: PendingFolder = {
    actor: managerActor(),
    userId: checks.userId,
    spaceId: checks.spaceId,
    folderId: folder.id,
    folderName: folder.name,
    createdAt: folder.created_at,
  };
  const cleanup = () => cleanupFolder(checks, pending);
  try {
    const token = crypto.randomUUID();
    const text = input?.marker ?? `Self-test reference: the verification phrase is amber orchard ${token}.`;
    const file = inputFile ?? new File([text], "self-test.txt", { type: "text/plain" });
    const transfer = runManagerImport(
      checks.dispatch as ManagerDispatch,
      checks.spaceId,
      [{ folderId: folder.id, file }],
      "fast",
    );
    const transferEntry = managerImportsSnapshot().find(
      (entry) => entry.folderId === folder.id && entry.spaceId === checks.spaceId,
    );
    if (transferEntry) {
      pending.uploadKey = transferEntry.key;
    }
    await transfer;
    const imported = managerImportsSnapshot().find((entry) => entry.folderId === folder.id);
    assert(imported?.receipt, "Import manager did not resolve a durable upload receipt.");
    const receipt = imported.receipt;
    assert(
      receipt.status === "stored" &&
        receipt.document_id &&
        receipt.folder_id === folder.id &&
        receipt.space_id === checks.spaceId,
      "Document upload did not return a stored document in the disposable folder.",
    );
    const documentId = receipt.document_id;
    pending.documentId = documentId;
    const bounded = AbortSignal.any([signal, AbortSignal.timeout(120_000)]);
    while (true) {
      bounded.throwIfAborted();
      const directory = await checks
        .dispatch(cp.entries.initiate({ id: checks.spaceId, parentId: folder.id }, FRESH))
        .unwrap();
      const document = directory.items.find((entry) => entry.kind === "document" && entry.data.id === documentId);
      const processing = directory.processing[documentId];
      assert(processing?.status !== "failed", "Document ingestion failed.");
      if (processing?.status === "succeeded") {
        assert(document?.kind === "document", "Ingested document is missing from its folder.");
        if (input?.tabular)
          assert(typeof processing.rows === "number" && processing.rows > 0, "Ingestion published no tabular rows.");
        else assert(processing.chunks > 0 && processing.vectors > 0, "Ingestion produced no searchable content.");
        await dismissManagerImport(checks.dispatch as ManagerDispatch, receipt.request_key);
        return {
          folderId: folder.id,
          documentId,
          text,
          cleanup,
          renameFolder: async (newName: string) => {
            assert(newName.startsWith("Self-test "), "Disposable folder names must retain their marker.");
            await checks.dispatch(cp.renameFolder.initiate({ id: folder.id, rename: { name: newName } })).unwrap();
            pending.folderName = newName;
          },
        };
      }
      await pause(bounded);
    }
  } catch (error) {
    try {
      await cleanup();
    } catch (cleanupError) {
      if (cleanupError instanceof SkipStep)
        throw new Error("The fixture did not finish and its cleanup remains incomplete.");
      throw new Error("Knowledge fixture failed and its cleanup could not be verified.");
    }
    throw error;
  }
}
