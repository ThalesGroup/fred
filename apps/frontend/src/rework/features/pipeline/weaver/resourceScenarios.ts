// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { ManagedAgentInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { FRESH } from "../deps/api";
import { countMarketplacePrompts, createPromptsDeps } from "../deps/prompts";
import { tabularFixtures } from "../scenarios/formats";
import { promptsScenario } from "../scenarios/promptsScenario";
import { expectRefused } from "../scenarios/runScope";
import { runStep, SkipStep } from "../step";
import type { Reporter, Scenario } from "../types";
import type { WeaverChecks } from "./checks";
import { promptPublication, teamWiki } from "./editorialScenarios";
import {
  TEST_ASSISTANT,
  checkKnowledgeRuntime,
  checkAgentRuntime,
  checkConversationRuntime,
  runRuntimeProbe,
} from "./runtime";
import {
  assert,
  cp,
  expectAbsent,
  ingestKnowledgeFixture,
  provisionDisposableAgent,
  requireSpace,
  requireWrite,
  requireCapabilities,
  waitForDeletion,
  registerTestConversation,
  deleteTestConversation,
  pause,
  folderListed,
} from "./resourceSupport";

async function deleteAgent(checks: WeaverChecks, agent: ManagedAgentInstanceSummary) {
  const args = { spaceId: checks.spaceId, agentInstanceId: agent.agent_instance_id };
  await checks.dispatch(cp.deleteAgentInstance.initiate(args)).unwrap();
  await expectAbsent(() => checks.dispatch(cp.getAgentInstance.initiate(args, FRESH)).unwrap());
  const catalog = await checks.dispatch(cp.listAgentInstances.initiate({ spaceId: checks.spaceId }, FRESH)).unwrap();
  assert(
    !catalog.items.some((item) => item.agent_instance_id === agent.agent_instance_id),
    "Deleted agent remains in its catalog.",
  );
}

async function unavailable(report: Reporter, id: string, title: string, reason: string) {
  await runStep(report, id, title, async () => {
    throw new SkipStep(reason);
  });
}

async function enableDocumentAccess(checks: WeaverChecks, agent: ManagedAgentInstanceSummary, signal: AbortSignal) {
  signal.throwIfAborted();
  if (agent.source_agent_id !== TEST_ASSISTANT)
    throw new SkipStep("The deterministic diagnostic template is not available; resource management remains covered.");
  await requireCapabilities(checks, agent.source_runtime_id, ["document_access"]);
  return checks
    .dispatch(
      cp.updateAgentInstance.initiate({
        spaceId: checks.spaceId,
        agentInstanceId: agent.agent_instance_id,
        updateAgentInstanceRequest: { capability_ids: ["document_access"] },
      }),
    )
    .unwrap();
}

const knowledgeText: Scenario<WeaverChecks> = async (checks, report, signal) => {
  let fixture: Awaited<ReturnType<typeof ingestKnowledgeFixture>> | null = null;
  let agent: ManagedAgentInstanceSummary | null = null;
  try {
    fixture = await ingestKnowledgeFixture(checks, signal, undefined, {
      report,
      id: "knowledge.ingest",
      title: "Upload and index a disposable document",
      detail: "The import manager stored the upload and ingestion published chunks and vectors.",
    });
    if (!fixture) {
      await unavailable(
        report,
        "runtime-retrieval",
        "Retrieve the document through its trusted runtime scope",
        checks.spaceKind === "organization"
          ? "Retrieval requires an agent in a team, project or personal space; this is the organization level."
          : "The disposable document was not published; retrieval requires a published fixture.",
      );
      return;
    }
    const owned = fixture;
    await runStep(report, "knowledge.list", "Read back the document, folder and processing history", async () => {
      signal.throwIfAborted();
      const directory = await checks
        .dispatch(cp.entries.initiate({ id: checks.spaceId, parentId: owned.folderId }, FRESH))
        .unwrap();
      assert(
        directory.items.some((entry) => entry.kind === "document" && entry.data.id === owned.documentId),
        "The uploaded document is absent from the directory.",
      );
      const history = await checks.dispatch(cp.history.initiate({ id: owned.documentId }, FRESH)).unwrap();
      assert(
        history.some((attempt) => attempt.status === "succeeded"),
        "The document has no successful processing history.",
      );
      const renamed = `Self-test updated ${crypto.randomUUID()}`;
      await owned.renameFolder(renamed);
      const root = await checks.dispatch(cp.entries.initiate({ id: checks.spaceId, search: renamed }, FRESH)).unwrap();
      assert(
        root.items.some(
          (entry) => entry.kind === "folder" && entry.data.id === owned.folderId && entry.data.name === renamed,
        ),
        "Folder rename did not round-trip.",
      );
      return { value: true };
    });
    if (checks.spaceKind === "organization") {
      await unavailable(
        report,
        "runtime-retrieval",
        "Retrieve the document through its trusted runtime scope",
        "Retrieval requires an agent in a team, project or personal space; this is the organization level.",
      );
      return;
    }
    agent = await runStep(report, "knowledge.agent", "Provision the deterministic retrieval agent", async () => ({
      value: await provisionDisposableAgent(checks, signal, "knowledge", TEST_ASSISTANT, ["document_access"]),
    }));
    if (agent) {
      const diagnostic = agent;
      await runStep(report, "knowledge.retrievable", "Exclude the document from search and restore it", async () => {
        signal.throwIfAborted();
        const hidden = await checks
          .dispatch(cp.setRetrievable.initiate({ id: owned.documentId, setRetrievable: { retrievable: false } }))
          .unwrap();
        assert(!hidden.retrievable, "The document was not excluded from retrieval.");
        try {
          const result = await runRuntimeProbe(
            checks,
            diagnostic.agent_instance_id,
            signal,
            { mode: "retrieval", query: owned.text, marker: owned.text },
            { runtimeContext: { selected_document_uids: [owned.documentId], search_rag_scope: "corpus_only" } },
          );
          assert(result.report.before === false, "The excluded document was returned by protected search.");
        } finally {
          await checks
            .dispatch(cp.setRetrievable.initiate({ id: owned.documentId, setRetrievable: { retrievable: true } }))
            .unwrap();
        }
        const bounded = AbortSignal.any([signal, AbortSignal.timeout(60_000)]);
        while (true) {
          bounded.throwIfAborted();
          const directory = await checks
            .dispatch(cp.entries.initiate({ id: checks.spaceId, parentId: owned.folderId }, FRESH))
            .unwrap();
          if (
            directory.items.some(
              (entry) =>
                entry.kind === "document" &&
                entry.data.id === owned.documentId &&
                entry.data.retrievable &&
                !entry.data.retrievable_pending,
            )
          )
            break;
          await pause(bounded);
        }
        return { value: true };
      });
      await checkKnowledgeRuntime(checks, report, signal, agent, owned);
    } else
      await unavailable(
        report,
        "runtime-retrieval",
        "Retrieve the document through its trusted runtime scope",
        "The required diagnostic agent or document capability could not be provisioned.",
      );
  } finally {
    if (fixture)
      await runStep(report, "knowledge.cleanup", "Delete the document and folder and verify removal", async () => {
        await fixture!.cleanup();
        return { value: true };
      });
    if (agent)
      await runStep(report, "knowledge.agentCleanup", "Delete the retrieval agent and verify removal", async () => {
        await deleteAgent(checks, agent!);
        return { value: true };
      });
  }
};

export const agents: Scenario<WeaverChecks> = async (checks, report, signal) => {
  const agent = await runStep(report, "agents.create", "Provision an authorized agent template", async () => ({
    value: await provisionDisposableAgent(checks, signal, "agent"),
  }));
  if (!agent) return;
  const args = { spaceId: checks.spaceId, agentInstanceId: agent.agent_instance_id };
  try {
    await runStep(report, "agents.update", "Rename the agent and retain its immutable logical name", async () => {
      signal.throwIfAborted();
      const name = `${agent.display_name} updated`;
      await checks
        .dispatch(cp.updateAgentInstance.initiate({ ...args, updateAgentInstanceRequest: { display_name: name } }))
        .unwrap();
      const saved = await checks.dispatch(cp.getAgentInstance.initiate(args, FRESH)).unwrap();
      assert(
        saved.display_name === name &&
          saved.template_id === agent.template_id &&
          saved.logical_name === agent.logical_name,
        "Agent identity or display name did not round-trip.",
      );
      const list = await checks.dispatch(cp.listAgentInstances.initiate({ spaceId: checks.spaceId }, FRESH)).unwrap();
      assert(
        list.items.some(
          (item) => item.agent_instance_id === agent.agent_instance_id && item.logical_name === agent.logical_name,
        ),
        "The managed agent is missing from its catalog.",
      );
      return { value: true };
    });
    await runStep(report, "agents.tuning", "Change and read back a template tuning field", async () => {
      signal.throwIfAborted();
      const templates = await checks
        .dispatch(cp.spaceAgentTemplates.initiate({ spaceId: checks.spaceId }, FRESH))
        .unwrap();
      const template = templates.find((item) => item.template_id === agent.template_id);
      const field = template?.default_tuning_fields.find(
        (item) =>
          typeof item.key === "string" &&
          (item.type === "boolean" || (item.type === "string" && !item.pattern && !item.enum)),
      );
      if (!field)
        throw new SkipStep(
          "The template advertises no independently mutable boolean or unconstrained string tuning field.",
        );
      const value = field.type === "boolean" ? !agent.tuning_field_values[field.key] : "Disposable self-test tuning.";
      await checks
        .dispatch(
          cp.updateAgentInstance.initiate({
            ...args,
            updateAgentInstanceRequest: { tuning_field_values: { ...agent.tuning_field_values, [field.key]: value } },
          }),
        )
        .unwrap();
      const saved = await checks.dispatch(cp.getAgentInstance.initiate(args, FRESH)).unwrap();
      assert(saved.tuning_field_values[field.key] === value, "Agent tuning did not round-trip.");
      return { value: true };
    });
    await runStep(
      report,
      "agents.status",
      "Reject execution preparation while disabled and restore the agent",
      async () => {
        signal.throwIfAborted();
        try {
          await checks
            .dispatch(cp.updateAgentInstance.initiate({ ...args, updateAgentInstanceRequest: { status: "disabled" } }))
            .unwrap();
          const saved = await checks.dispatch(cp.getAgentInstance.initiate(args, FRESH)).unwrap();
          assert(saved.status === "disabled", "Agent status did not round-trip.");
          let refused = false;
          try {
            await checks.dispatch(cp.prepareExecution.initiate(args)).unwrap();
          } catch (error) {
            const failure = error as { status?: unknown; data?: { code?: unknown } };
            assert(
              failure.status === 409 && failure.data?.code === "agent_instance_disabled",
              "Preparation failed for a reason other than the disabled agent.",
            );
            refused = true;
          }
          assert(refused, "The disabled agent still permits execution preparation.");
        } finally {
          await checks
            .dispatch(cp.updateAgentInstance.initiate({ ...args, updateAgentInstanceRequest: { status: "enabled" } }))
            .unwrap();
        }
        const restored = await checks.dispatch(cp.getAgentInstance.initiate(args, FRESH)).unwrap();
        assert(restored.status === "enabled", "The agent was not re-enabled.");
        const prepared = await checks.dispatch(cp.prepareExecution.initiate(args)).unwrap();
        assert(
          prepared.agent_instance_id === agent.agent_instance_id && prepared.space_id === checks.spaceId,
          "Re-enabled preparation did not resolve the expected agent and space.",
        );
        return { value: true };
      },
    );
    if (agent.source_agent_id === TEST_ASSISTANT) await checkAgentRuntime(checks, report, signal, agent);
    else
      await unavailable(
        report,
        "runtime-echo",
        "Verify deterministic execution without a model",
        "The diagnostic template is unavailable; generic agent management was still checked.",
      );
    await unavailable(
      report,
      "agents.copy",
      "Copy an agent between spaces",
      "The current generated management contract exposes no agent-copy operation.",
    );
  } finally {
    await runStep(
      report,
      "agents.cleanup",
      "Delete the agent and verify its absence from reads and lists",
      async () => {
        await deleteAgent(checks, agent);
        return { value: true };
      },
    );
  }
};

export const conversations: Scenario<WeaverChecks> = async (checks, report, signal) => {
  const agent = await runStep(report, "conversations.agent", "Provision the conversation agent", async () => ({
    value: await provisionDisposableAgent(checks, signal, "conversation"),
  }));
  if (!agent) return;
  const sessions: string[] = [];
  const spaceId = checks.spaceId;
  try {
    const configured = await runStep(
      report,
      "conversations.capability",
      "Enable authorized attachment access on the diagnostic agent",
      async () => ({ value: await enableDocumentAccess(checks, agent, signal) }),
    );
    await runStep(report, "conversations.create", "Prepare and register two isolated conversations", async () => {
      signal.throwIfAborted();
      const preparation = await checks
        .dispatch(cp.prepareExecution.initiate({ spaceId, agentInstanceId: agent.agent_instance_id }))
        .unwrap();
      for (let index = 0; index < 2; index++) {
        signal.throwIfAborted();
        sessions.push(
          await registerTestConversation(checks, agent.agent_instance_id, preparation.agent_configuration_revision),
        );
      }
      return { value: true };
    });
    await runStep(report, "conversations.update", "Rename and list the registered conversation", async () => {
      signal.throwIfAborted();
      if (!sessions.length) throw new SkipStep("Conversation registration did not complete.");
      const args = { spaceId, sessionId: sessions[0] };
      await checks
        .dispatch(
          cp.updateSession.initiate({ ...args, updateSessionRequest: { title: "Updated disposable conversation" } }),
        )
        .unwrap();
      const saved = await checks.dispatch(cp.getSession.initiate(args, FRESH)).unwrap();
      assert(
        saved.title === "Updated disposable conversation" && saved.agent_instance_id === agent.agent_instance_id,
        "Conversation update did not round-trip.",
      );
      const list = await checks.dispatch(cp.listSessions.initiate({ spaceId }, FRESH)).unwrap();
      assert(
        sessions.every((id) => list.some((item) => item.session_id === id)),
        "Registered conversations are missing from the list.",
      );
      return { value: true };
    });
    if (configured && sessions.length === 2)
      await checkConversationRuntime(checks, report, signal, configured, sessions);
    else
      await unavailable(
        report,
        "runtime-attachment-isolation",
        "Verify attachment retrieval is confined to its conversation",
        "Two conversations and an authorized diagnostic document capability are required.",
      );
    await unavailable(
      report,
      "conversations.prompts",
      "Attach context prompts to a conversation",
      "The current conversation-management contract exposes no context-prompt attachment operation.",
    );
  } finally {
    for (const sessionId of sessions)
      await runStep(
        report,
        `conversations.cleanup.${sessions.indexOf(sessionId)}`,
        "Delete the conversation and verify removal",
        async () => {
          const detail = await deleteTestConversation(checks, sessionId);
          return { value: true, detail };
        },
      );
    await runStep(report, "conversations.agentCleanup", "Delete the conversation agent", async () => {
      await deleteAgent(checks, agent);
      return { value: true };
    });
  }
};
export const prompts: Scenario<WeaverChecks> = async (checks, report, signal) => {
  if (checks.spaceKind === "organization")
    await runStep(report, "prompts.market", "Read the authorized prompt marketplace", async () => {
      requireSpace(checks, signal);
      const count = await countMarketplacePrompts(checks.read, checks.organizationId);
      return { value: true, detail: `${count} published prompt(s)` };
    });
  await promptsScenario(
    createPromptsDeps(checks.dispatch, checks.read, async () => {
      await requireWrite(checks, signal);
      return checks.spaceId;
    }),
    report,
    signal,
  );
  if (checks.spaceKind === "organization") await promptPublication(checks, report, signal);
};

export const teams: Scenario<WeaverChecks> = async (checks, report, signal) => {
  const team = await runStep(
    report,
    "teams.create",
    "Create a disposable team with the current person as owner",
    async () => {
      requireSpace(checks, signal);
      if (!checks.organizationId || !checks.userId)
        throw new SkipStep("An organization and signed-in person are required.");
      const allowed = await checks
        .dispatch(cp.authorizeSpace.initiate({ spaceCheck: { space_id: checks.organizationId, permission: "manage" } }))
        .unwrap();
      if (!allowed.allowed) throw new SkipStep("The current person cannot create teams in the selected organization.");
      return {
        value: await checks
          .dispatch(
            cp.createSpace.initiate({
              createSpace: {
                kind: "team",
                name: `Self-test ${crypto.randomUUID()}`,
                owner: checks.userId,
                parent_id: checks.organizationId,
              },
            }),
          )
          .unwrap(),
      };
    },
  );
  if (!team) return;
  const editorGrant = { id: team.id, user: checks.userId, role: "editor" as const };
  let editorMayExist = false;
  const deniedContent = async () => {
    signal.throwIfAborted();
    await expectRefused(
      () => checks.dispatch(cp.entries.initiate({ id: team.id }, FRESH)).unwrap(),
      "Owner-only content read",
      [403],
    );
    await expectRefused(
      () =>
        checks
          .dispatch(
            cp.createPrompt.initiate({
              spaceId: team.id,
              createPromptRequest: {
                display_name: "Disposable denied prompt",
                logical_name: `self-test-${crypto.randomUUID()}`,
                text: "Disposable permission probe.",
              },
            }),
          )
          .unwrap(),
      "Owner-only content write",
      [403],
    );
  };
  try {
    const ownerOnly = await runStep(
      report,
      "teams.read",
      "Verify owner governance without content access",
      async () => {
        signal.throwIfAborted();
        const spaces = await checks.dispatch(cp.mySpaces.initiate(undefined, FRESH)).unwrap();
        const saved = spaces.find((space) => space.id === team.id);
        assert(
          saved?.kind === "team" && saved.roles.includes("owner"),
          "Created team is not visible with the assigned owner role.",
        );
        const members = await checks.dispatch(cp.spaceMembers.initiate({ id: team.id }, FRESH)).unwrap();
        assert(
          members.items.some((member) => member.user.id === checks.userId && member.roles.includes("owner")),
          "Owner membership is missing.",
        );
        assert(!saved.roles.includes("editor"), "The disposable team unexpectedly grants editor access.");
        const governance = await checks
          .dispatch(
            cp.authorizeSpace.initiate({
              spaceCheck: { space_id: team.id, permission: "manage" },
            }),
          )
          .unwrap();
        assert(governance.allowed, "The owner cannot manage the disposable team.");
        await deniedContent();
        return { value: true };
      },
    );
    if (!ownerOnly) return;
    const editor = await runStep(
      report,
      "teams.grantEditor",
      "Explicitly grant content editing on the disposable team",
      async () => {
        signal.throwIfAborted();
        editorMayExist = true;
        await checks.dispatch(cp.grant.initiate(editorGrant)).unwrap();
        const directory = await checks.dispatch(cp.entries.initiate({ id: team.id }, FRESH)).unwrap();
        assert(directory.total === 0, "Disposable team was not created empty.");
        return { value: true };
      },
    );
    if (!editor) return;
    await runStep(report, "teams.prompt", "Create and read back a prompt in the disposable team", async () => {
      signal.throwIfAborted();
      const prompt = await checks
        .dispatch(
          cp.createPrompt.initiate({
            spaceId: team.id,
            createPromptRequest: {
              display_name: "Disposable team prompt",
              logical_name: `self-test-${crypto.randomUUID()}`,
              text: "Team-scoped disposable text.",
            },
          }),
        )
        .unwrap();
      try {
        const saved = await checks
          .dispatch(cp.getPrompt.initiate({ spaceId: team.id, promptId: prompt.prompt_id }, FRESH))
          .unwrap();
        assert(
          saved.space_id === team.id && saved.prompt_id === prompt.prompt_id && saved.text === prompt.text,
          "Team prompt scope or content did not round-trip.",
        );
      } finally {
        await checks.dispatch(cp.deletePrompt.initiate({ spaceId: team.id, promptId: prompt.prompt_id })).unwrap();
        await expectAbsent(() =>
          checks.dispatch(cp.getPrompt.initiate({ spaceId: team.id, promptId: prompt.prompt_id }, FRESH)).unwrap(),
        );
      }
      return { value: true };
    });
    await runStep(report, "teams.folder", "Create and list a folder in the disposable team", async () => {
      signal.throwIfAborted();
      const folder = await checks
        .dispatch(cp.createFolder.initiate({ createFolder: { space_id: team.id, name: "Disposable team folder" } }))
        .unwrap();
      try {
        const directory = await checks.dispatch(cp.entries.initiate({ id: team.id }, FRESH)).unwrap();
        assert(
          directory.items.some(
            (entry) => entry.kind === "folder" && entry.data.id === folder.id && entry.data.space_id === team.id,
          ),
          "The team folder is absent or incorrectly scoped.",
        );
      } finally {
        await checks.dispatch(cp.deleteFolder.initiate({ id: folder.id, emptyOnly: true })).unwrap();
        assert(
          !(await folderListed({ ...checks, spaceId: team.id }, folder.id)),
          "The deleted team folder remains listed.",
        );
      }
      return { value: true };
    });
    const teamChecks = { ...checks, spaceId: team.id, spaceKind: "team" as const };
    const teamAgent = await runStep(
      report,
      "teams.agent",
      "Provision and list an agent in the disposable team",
      async () => ({ value: await provisionDisposableAgent(teamChecks, signal, "team") }),
    );
    if (teamAgent)
      await runStep(report, "teams.agentScope", "Verify the agent stays in its team and remove it", async () => {
        try {
          signal.throwIfAborted();
          const saved = await checks
            .dispatch(
              cp.getAgentInstance.initiate({ spaceId: team.id, agentInstanceId: teamAgent.agent_instance_id }, FRESH),
            )
            .unwrap();
          const catalog = await checks.dispatch(cp.listAgentInstances.initiate({ spaceId: team.id }, FRESH)).unwrap();
          assert(
            saved.space_id === team.id &&
              catalog.items.some((item) => item.agent_instance_id === teamAgent.agent_instance_id),
            "The agent is not scoped to its team catalog.",
          );
        } finally {
          await deleteAgent(teamChecks, teamAgent);
        }
        return { value: true };
      });
    await teamWiki(teamChecks, report, signal);
    for (const [id, title, reason] of [
      [
        "joinLink",
        "Manage a disposable team join link",
        "The current generated management contract exposes no team join-link operations.",
      ],
      [
        "routing",
        "Read the team's model routing policy",
        "The current generated management contract exposes no team-routing policy operation.",
      ],
    ])
      await unavailable(report, `teams.${id}`, title, reason);
    await runStep(report, "teams.revokeEditor", "Revoke editing and verify owner-only content denial", async () => {
      await checks.dispatch(cp.revoke.initiate(editorGrant)).unwrap();
      editorMayExist = false;
      await deniedContent();
      return { value: true };
    });
  } finally {
    if (editorMayExist)
      await runStep(report, "teams.editorCleanup", "Remove the disposable editor grant", async () => {
        await checks.dispatch(cp.revoke.initiate(editorGrant)).unwrap();
        editorMayExist = false;
        return { value: true };
      });
    await runStep(report, "teams.cleanup", "Delete the disposable team and verify removal", async () => {
      const receipt = await checks.dispatch(cp.deleteSpace.initiate({ id: team.id, immediate: true })).unwrap();
      assert(
        receipt.target_kind === "team" &&
          receipt.target_id === team.id &&
          receipt.target_parent_id === checks.organizationId &&
          receipt.actor_subject === checks.userId,
        "The team deletion receipt does not match the disposable team.",
      );
      const spaces = await checks.dispatch(cp.mySpaces.initiate(undefined, FRESH)).unwrap();
      assert(!spaces.some((space) => space.id === team.id), "Deleted team remains accessible.");
      const outcome = await waitForDeletion(checks, receipt);
      if (!outcome.completed) throw new Error(outcome.detail);
      return { value: true, detail: outcome.detail };
    });
  }
};

const knowledgeSql: Scenario<WeaverChecks> = async (checks, report, signal) => {
  const agent = await runStep(
    report,
    "knowledge.sql.agent",
    "Provision the authorized tabular diagnostic agent",
    async () => ({
      value: await provisionDisposableAgent(checks, signal, "tabular", TEST_ASSISTANT, [
        "mcp-knowledge-flow-mcp-tabular",
      ]),
    }),
  );
  if (!agent) {
    for (const format of ["csv", "xlsx"])
      await unavailable(
        report,
        `knowledge.sql.${format}`,
        `Query the disposable ${format.toUpperCase()} dataset`,
        "The diagnostic template or delegated tabular capability is not advertised and permitted in this space.",
      );
    return;
  }
  try {
    for (const format of tabularFixtures(crypto.randomUUID().replaceAll("-", ""))) {
      const fixture = await ingestKnowledgeFixture(
        checks,
        signal,
        {
          file: format.build,
          marker: format.marker,
          tabular: true,
        },
        {
          report,
          id: `knowledge.sql.${format.id}.upload`,
          title: `Upload and publish a disposable ${format.id.toUpperCase()} dataset`,
        },
      );
      if (!fixture) {
        await unavailable(
          report,
          `knowledge.sql.${format.id}`,
          `Query the ${format.id.toUpperCase()} dataset through its admitted runtime`,
          "The scoped tabular fixture was not published.",
        );
        continue;
      }
      try {
        await runStep(
          report,
          `knowledge.sql.${format.id}`,
          `Discover, describe and query the ${format.id.toUpperCase()} dataset`,
          async () => {
            const result = await runRuntimeProbe(
              checks,
              agent.agent_instance_id,
              signal,
              { mode: "tabular", marker: format.marker },
              { runtimeContext: { selected_document_uids: [fixture.documentId], search_rag_scope: "corpus_only" } },
            );
            assert(result.report.tabular === true, "The scoped read-only SQL query did not return its fixture row.");
            return {
              value: true,
              detail:
                "The admitted diagnostic discovered the exact dataset, described its alias and returned the expected row through the bound read-only SQL tool.",
            };
          },
        );
      } finally {
        await runStep(
          report,
          `knowledge.sql.${format.id}.cleanup`,
          `Retire the ${format.id.toUpperCase()} document and remove its verified folder`,
          async () => {
            await fixture.cleanup();
            return { value: true };
          },
        );
      }
    }
  } finally {
    await runStep(report, "knowledge.sql.agentCleanup", "Delete the tabular diagnostic agent", async () => {
      await deleteAgent(checks, agent);
      return { value: true };
    });
  }
};

export const knowledge: Scenario<WeaverChecks> = async (checks, report, signal) => {
  await knowledgeText(checks, report, signal);
  if (checks.spaceKind === "organization") {
    for (const format of ["csv", "xlsx"])
      await unavailable(
        report,
        `knowledge.sql.${format}`,
        `Query the disposable ${format.toUpperCase()} dataset`,
        "Tabular runtime checks require an agent in a team, project or personal space; this is the organization level.",
      );
  } else await knowledgeSql(checks, report, signal);
};
