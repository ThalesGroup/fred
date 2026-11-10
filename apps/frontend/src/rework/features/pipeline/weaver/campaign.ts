// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { cp, waitForDeletion } from "./resourceSupport";
import type { Me, Role, SpacePermission } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { FRESH } from "../deps/api";
import { authedFetch } from "../useAuthzProbeRun";
import { runStep, SkipStep } from "../step";
import type { Reporter } from "../types";
import type { WeaverChecks } from "./checks";

export interface CampaignJournal {
  version: 1;
  operatorId: string;
  parentId: string;
  scope: string;
  projectId?: string;
  deletionId?: string;
}
export interface CampaignStorage {
  read(): CampaignJournal | null;
  save(value: CampaignJournal | null): void;
}
export const ROLE_PERMISSIONS: Record<Exclude<Role, "organization_admin">, SpacePermission[]> = {
  member: ["read", "create_personal_space"],
  editor: ["read", "write", "create_personal_space"],
  analyst: [
    "read",
    "run_evaluations",
    "manage_evaluation_corpus",
    "read_conversations_for_evaluation",
    "read_usage",
    "create_personal_space",
  ],
  owner: ["manage", "run_evaluations", "manage_evaluation_corpus", "read_usage", "create_personal_space"],
};
export const hasCampaignContentRole = (roles: readonly string[]): boolean =>
  roles.some((role) => ["member", "editor", "analyst"].includes(role));
const PERMISSIONS: SpacePermission[] = [
  "read",
  "write",
  "manage",
  "run_evaluations",
  "manage_evaluation_corpus",
  "read_conversations_for_evaluation",
  "read_usage",
  "administer_organization",
];
const nameOf = (journal: CampaignJournal) => `selftest-role-${journal.scope}`;
const safe = async <T>(operation: () => Promise<T>): Promise<T> => {
  try {
    return await operation();
  } catch {
    throw new Error("The campaign request failed; retry scoped recovery if needed");
  }
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export function validateJournal(value: CampaignJournal): void {
  if (
    value.version !== 1 ||
    typeof value.operatorId !== "string" ||
    !value.operatorId ||
    !UUID.test(value.parentId) ||
    !UUID.test(value.scope) ||
    Object.keys(value).some(
      (key) => !["version", "operatorId", "parentId", "scope", "projectId", "deletionId"].includes(key),
    ) ||
    (value.projectId !== undefined && !UUID.test(value.projectId)) ||
    (value.deletionId !== undefined && !UUID.test(value.deletionId))
  )
    throw new Error("Invalid recovery identifiers; manual inspection is required");
}
async function identity(context: WeaverChecks): Promise<Me> {
  const me = await safe(() => context.dispatch(cp.me.initiate(undefined, FRESH)).unwrap());
  if (me.user_id !== context.userId) throw new Error("The operator identity changed");
  return me;
}
export async function recoverCampaign(
  context: WeaverChecks,
  storage: CampaignStorage,
  report: Reporter,
): Promise<void> {
  await runStep(report, "campaign-cleanup", "Remove only the disposable campaign project", async () => {
    const journal = storage.read();
    if (!journal) return { value: true };
    validateJournal(journal);
    const operator = await identity(context);
    if (operator.user_id !== journal.operatorId || !operator.platform_roles.includes("platform_admin"))
      throw new Error("Recovery requires the original operator with platform administration access");
    const spaces = await safe(() => context.dispatch(cp.mySpaces.initiate(undefined, FRESH)).unwrap());
    let matches = spaces.filter(
      (space) =>
        space.parent_id === journal.parentId &&
        space.name === nameOf(journal) &&
        space.kind === "project" &&
        space.roles.includes("owner"),
    );
    if (matches.length > 1 || (journal.projectId && matches.some((space) => space.id !== journal.projectId)))
      throw new Error("The disposable project could not be uniquely verified");
    if (!journal.projectId && matches[0]) {
      journal.projectId = matches[0].id;
      storage.save(journal);
    }
    if (!journal.projectId) {
      try {
        await context
          .dispatch(
            cp.createSpace.initiate({
              createSpace: {
                kind: "project",
                name: nameOf(journal),
                parent_id: journal.parentId,
                owner: journal.operatorId,
              },
            }),
          )
          .unwrap();
      } catch (error) {
        if ((error as { status?: unknown })?.status !== 409)
          throw new Error("The exact disposable project could not be reconciled; retain recovery identifiers");
      }
      const reconciled = await safe(() => context.dispatch(cp.mySpaces.initiate(undefined, FRESH)).unwrap());
      matches = reconciled.filter(
        (space) =>
          space.parent_id === journal.parentId &&
          space.name === nameOf(journal) &&
          space.kind === "project" &&
          space.roles.includes("owner"),
      );
      if (matches.length !== 1) throw new Error("The exact disposable project could not be uniquely reconciled");
      journal.projectId = matches[0].id;
      storage.save(journal);
    }
    if (!journal.deletionId) {
      let receipt;
      if (matches.some((space) => space.id === journal.projectId)) {
        receipt = await safe(() =>
          context.dispatch(cp.deleteSpace.initiate({ id: journal.projectId!, immediate: true })).unwrap(),
        );
      } else {
        receipt = await safe(() =>
          context.dispatch(cp.projectDeletionStatus.initiate({ id: journal.projectId! }, FRESH)).unwrap(),
        );
      }
      if (
        receipt.target_id !== journal.projectId ||
        receipt.target_parent_id !== journal.parentId ||
        receipt.actor_subject !== journal.operatorId ||
        receipt.target_kind !== "project"
      )
        throw new Error("Cleanup receipt does not match the scoped campaign");
      journal.deletionId = receipt.id;
      storage.save(journal);
    }
    const receipt = await safe(() =>
      context.dispatch(cp.deletionStatus.initiate({ operationId: journal.deletionId! }, FRESH)).unwrap(),
    );
    if (
      receipt.target_id !== journal.projectId ||
      receipt.target_parent_id !== journal.parentId ||
      receipt.actor_subject !== journal.operatorId ||
      receipt.target_kind !== "project"
    )
      throw new Error("Cleanup receipt does not match the project");
    const visible = await safe(() => context.dispatch(cp.mySpaces.initiate(undefined, FRESH)).unwrap());
    if (visible.some((space) => space.id === journal.projectId))
      throw new Error("The retired project remains visible; retain recovery identifiers");
    storage.save(null);
    try {
      const outcome = await waitForDeletion(context, receipt);
      if (!outcome.completed) {
        if (Date.parse(receipt.due_at) > Date.now()) throw new SkipStep(outcome.detail);
        throw new Error("Physical deletion did not complete within the cleanup observation window");
      }
    } catch (error) {
      if (error instanceof SkipStep) throw error;
      throw new Error("Project retirement is verified; physical deletion has not completed");
    }
    return { value: true, detail: "Disposable project deletion completed" };
  });
}
export async function runCampaign(
  context: WeaverChecks,
  token: string,
  storage: CampaignStorage,
  report: Reporter,
  signal: AbortSignal,
): Promise<void> {
  const ready = await runStep(
    report,
    "campaign-preflight",
    "Verify independent identities and parent eligibility",
    async () => {
      if (storage.read()) throw new Error("Recover the interrupted campaign first");
      const configuration = await safe(() => context.dispatch(cp.frontendConfig.initiate(undefined, FRESH)).unwrap());
      if (!configuration.user_auth.enabled) throw new Error("The campaign requires real token authentication");
      const operator = await identity(context);
      if (!operator.platform_roles.includes("platform_admin"))
        throw new Error("Platform administration access is required for project cleanup");
      const target = await safe(() => authedFetch("/control-plane/v1/me", token));
      const user = target.body as Me;
      if (target.status !== 200 || !user?.user_id || user.user_id === context.userId)
        throw new Error("Supply a different, authenticated test account");
      const spaces = await safe(() => context.dispatch(cp.mySpaces.initiate(undefined, FRESH)).unwrap());
      const parent = spaces.find((space) => space.id === context.spaceId);
      if (parent?.kind !== "team" || !parent.roles.includes("owner") || !hasCampaignContentRole(parent.roles))
        throw new Error("Select a team where the operator has owner and content roles");
      const available = await safe(() => authedFetch("/control-plane/v1/me/spaces", token));
      if (
        available.status !== 200 ||
        !Array.isArray(available.body) ||
        !available.body.some((space) => space.id === parent.id && hasCampaignContentRole(space.roles ?? []))
      )
        throw new Error("The test account needs an existing content role on the selected parent team");
      const journal: CampaignJournal = {
        version: 1,
        operatorId: context.userId,
        parentId: parent.id,
        scope: crypto.randomUUID(),
      };
      storage.save(journal);
      return { value: { journal, targetId: user.user_id } };
    },
  );
  if (!ready) return;
  const { journal, targetId } = ready;
  const active = async () => {
    if (signal.aborted) throw new Error("Campaign interrupted; recover scoped resources");
    await identity(context);
    const target = await safe(() => authedFetch("/control-plane/v1/me", token));
    if (target.status !== 200 || (target.body as Me)?.user_id !== targetId)
      throw new Error("The test credential expired or changed");
  };
  try {
    let created;
    try {
      created = await context
        .dispatch(
          cp.createSpace.initiate({
            createSpace: { kind: "project", name: nameOf(journal), parent_id: journal.parentId, owner: context.userId },
          }),
        )
        .unwrap();
    } catch (error) {
      const status = (error as { status?: unknown })?.status;
      if (typeof status === "number" && [400, 403, 404, 409, 422].includes(status)) storage.save(null);
      throw new Error("The disposable project could not be created");
    }
    journal.projectId = created.id;
    storage.save(journal);
    for (const role of [null, "member", "editor", "analyst", "owner"] as const) {
      const passed = await runStep(
        report,
        `campaign-role-${role ?? "none"}`,
        `Check disposable project permissions: ${role ?? "no direct role"}`,
        async () => {
          await active();
          if (role)
            await safe(() => context.dispatch(cp.grant.initiate({ id: created.id, role, user: targetId })).unwrap());
          const expected = role ? ROLE_PERMISSIONS[role] : [];
          for (const permission of PERMISSIONS) {
            const response = await safe(() =>
              authedFetch("/control-plane/v1/authorize/space", token, {
                method: "POST",
                body: { space_id: created.id, permission },
              }),
            );
            if (
              response.status !== 200 ||
              (response.body as { allowed?: boolean })?.allowed !== expected.includes(permission)
            )
              throw new Error(`Permission decision mismatch: ${permission}`);
          }
          const content = await safe(() =>
            authedFetch(`/control-plane/v1/spaces/${encodeURIComponent(created.id)}/entries`, token),
          );
          if (expected.includes("read") ? content.status !== 200 : ![403, 404].includes(content.status))
            throw new Error("Content read does not match the direct role");
          const management = await safe(() =>
            authedFetch(`/control-plane/v1/spaces/${encodeURIComponent(created.id)}/members`, token),
          );
          if (expected.includes("manage") ? management.status !== 200 : ![403, 404].includes(management.status))
            throw new Error("Membership management does not match the direct role");
          const write = await safe(() =>
            authedFetch("/control-plane/v1/folders", token, {
              method: "POST",
              body: { space_id: created.id, name: `role-${role ?? "none"}-${crypto.randomUUID()}` },
            }),
          );
          if (expected.includes("write") ? write.status !== 201 : ![403, 404].includes(write.status))
            throw new Error("Content write does not match the direct role");
          if (role)
            await safe(() => context.dispatch(cp.revoke.initiate({ id: created.id, role, user: targetId })).unwrap());
          const revoked = await safe(() =>
            authedFetch(`/control-plane/v1/spaces/${encodeURIComponent(created.id)}/entries`, token),
          );
          if (![403, 404].includes(revoked.status)) throw new Error("Content access remains after revocation");
          const revokedWrite = await safe(() =>
            authedFetch("/control-plane/v1/folders", token, {
              method: "POST",
              body: { space_id: created.id, name: `revoked-${crypto.randomUUID()}` },
            }),
          );
          if (![403, 404].includes(revokedWrite.status)) throw new Error("Content write remains after revocation");
          return { value: true };
        },
      );
      if (!passed) break;
    }
  } catch {
    await runStep(report, "campaign-interrupted", "Complete the isolated role matrix", async () => {
      throw new Error("The campaign was interrupted; scoped cleanup follows");
    });
  } finally {
    await recoverCampaign(context, storage, report);
  }
}
