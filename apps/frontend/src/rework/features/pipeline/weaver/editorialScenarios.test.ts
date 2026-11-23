// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StepReport } from "../types";
import type { WeaverChecks } from "./checks";

const mock = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: {
    endpoints: new Proxy({}, { get: (_target, name) => ({ initiate: (args: unknown) => ({ name, args }) }) }),
  },
}));
import { promptPublication, teamWiki } from "./editorialScenarios";

const checks = {
  spaceId: "organization",
  organizationId: "organization",
  userId: "operator",
  dispatch: (request: unknown) => ({ unwrap: () => mock.invoke(request) }),
} as unknown as WeaverChecks;
let reports: StepReport[];
let controller: AbortController;
const calls = (name: string) =>
  mock.invoke.mock.calls.map(([request]) => request).filter((request) => request.name === name);
const passed = (id: string) => expect(reports).toContainEqual(expect.objectContaining({ id, status: "passed" }));
const failed = (id: string) => expect(reports).toContainEqual(expect.objectContaining({ id, status: "failed" }));
beforeEach(() => {
  vi.clearAllMocks();
  reports = [];
  controller = new AbortController();
});

describe("disposable team wiki", () => {
  const run = () =>
    teamWiki({ ...checks, spaceId: "team", spaceKind: "team" }, (step) => reports.push(step), controller.signal);
  function wikiApi(
    options: { disabled?: boolean; editFailure?: boolean; staleHistory?: boolean; abortAfterCreate?: boolean } = {},
  ) {
    let deleted = false;
    let content = "";
    let original = "";
    let revision = "initial";
    const page = { page_id: "page-uuid", slug: "page-slug" };
    mock.invoke.mockImplementation(async ({ name, args }) => {
      if (name === "authorizeSpace") return { allowed: true };
      expect(args.spaceId).toBe("team");
      switch (name) {
        case "wikiAvailability":
          return { enabled: !options.disabled };
        case "createWikiPage":
          original = content = args.createWikiPageRequest.content_md;
          if (options.abortAfterCreate) controller.abort();
          return { page, content_md: content, revision_id: revision };
        case "writeWikiPage":
          expect(args.pageId).toBe(page.page_id);
          expect(args.updateWikiContentRequest.base_revision_id).toBe(revision);
          if (options.editFailure) throw { status: 409 };
          content = args.updateWikiContentRequest.content_md;
          revision = "revised";
          return { page, content_md: content, revision_id: revision };
        case "wikiPage":
          expect(args.pageId).toBe(page.slug);
          if (deleted) throw { status: 404 };
          return { page, content_md: content, revision_id: revision };
        case "wikiRevisions":
          expect(args.pageId).toBe(page.page_id);
          return {
            revisions: [
              { revision_id: "initial", status: "superseded" },
              { revision_id: "revised", status: "published" },
            ],
            contents: { initial: original, revised: options.staleHistory ? original : content },
          };
        case "deleteWikiPage":
          expect(args.pageId).toBe(page.page_id);
          deleted = true;
          return;
        case "wikiPages":
          return { pages: deleted ? [] : [page] };
        default:
          throw new Error("Unexpected wiki request");
      }
    });
  }
  it("uses the slug for reads, revision IDs for edits, and removes the page", async () => {
    wikiApi();
    await run();
    for (const id of ["teams.wiki", "teams.wikiRevision", "teams.wikiCleanup"]) passed(id);
  });
  it("skips an unavailable capability without creating a page", async () => {
    wikiApi({ disabled: true });
    await run();
    expect(reports).toContainEqual(expect.objectContaining({ id: "teams.wiki", status: "skipped" }));
    expect(calls("createWikiPage")).toHaveLength(0);
  });
  it.each([{ editFailure: true }, { staleHistory: true }, { abortAfterCreate: true }])(
    "cleans up after a revision failure or cancellation: %j",
    async (options) => {
      wikiApi(options);
      await run();
      failed("teams.wikiRevision");
      passed("teams.wikiCleanup");
    },
  );
});

describe("prompt marketplace publication", () => {
  const run = () => promptPublication(checks, (step) => reports.push(step), controller.signal);
  function publicationApi(
    options: {
      denied?: boolean;
      pending?: boolean;
      retainContent?: boolean;
      loseSubmission?: boolean;
      wrongSnapshot?: boolean;
      failWithdrawal?: boolean;
      foreignPublication?: boolean;
    } = {},
  ) {
    let state = options.pending ? "pending" : "approved";
    let version = options.pending ? 0 : 1;
    let published: string | null = options.pending ? null : "proposal";
    let removed = false;
    let sourceDeleted = false;
    let submissionKey: string | undefined;
    let source = {
      prompt_id: "source",
      space_id: "organization",
      logical_name: "",
      text: "",
      updated_at: "2026-01-01T00:00:00Z",
    };
    const proposal = () => ({
      proposal_id: "proposal",
      entry_id: "entry",
      state,
      publication_version: version,
      published_proposal_id: options.foreignPublication && published ? "foreign" : published,
      proposing_space_id: "organization",
      marketplace_space_id: "organization",
      submitted_by: "operator",
      actions: { can_decide: state === "pending" },
      package: { kind: "prompt", content: { logical_name: source.logical_name, text: source.text } },
    });
    mock.invoke.mockImplementation(async ({ name, args }) => {
      switch (name) {
        case "authorizeSpace":
          return { allowed: !options.denied };
        case "createPrompt":
          source = { ...source, ...args.createPromptRequest };
          return source;
        case "submitMarketplaceProposal":
          if (removed) throw { status: 409, data: { code: "proposal_removed" } };
          expect(args.submitProposalRequest).toEqual({
            kind: "prompt",
            source_space_id: "organization",
            source_resource_id: source.prompt_id,
            expected_revision: source.updated_at,
          });
          if (submissionKey) expect(args["Idempotency-Key"]).toBe(submissionKey);
          else {
            submissionKey = args["Idempotency-Key"];
            if (options.loseSubmission) throw { status: "FETCH_ERROR" };
          }
          return proposal();
        case "marketplaceProposal":
          if (removed && !options.retainContent) throw { status: 404 };
          return proposal();
        case "marketplaceEntry":
          if (!published) throw { status: 404 };
          return {
            proposal_id: published,
            publication_version: version,
            package: {
              kind: "prompt",
              content: {
                logical_name: source.logical_name,
                text: options.wrongSnapshot ? "Wrong content" : source.text,
              },
            },
          };
        case "cancelMarketplaceProposal":
          expect(state).toBe("pending");
          state = "cancelled";
          removed = true;
          return proposal();
        case "withdrawMarketplaceEntry":
          expect(args.entryId).toBe("entry");
          expect(args.withdrawRequest.expected_publication_version).toBe(version);
          if (options.failWithdrawal) throw { status: 503 };
          published = null;
          removed = true;
          version++;
          return;
        case "deletePrompt":
          sourceDeleted = true;
          return;
        case "getPrompt":
          if (sourceDeleted) throw { status: 404 };
          return source;
        default:
          throw new Error("Unexpected publication request");
      }
    });
  }
  it("publishes the captured source revision and withdraws using the current version", async () => {
    publicationApi();
    await run();
    for (const id of [
      "prompts.publicationCreate",
      "prompts.publication",
      "prompts.publicationWithdraw",
      "prompts.publicationCleanup",
    ])
      passed(id);
    expect(calls("decideMarketplaceProposal")).toHaveLength(0);
    expect(calls("cancelMarketplaceProposal")).toHaveLength(0);
    expect(calls("withdrawMarketplaceEntry")).toHaveLength(1);
  });
  it("skips before mutation when content write is missing", async () => {
    publicationApi({ denied: true });
    await run();
    expect(reports).toContainEqual(expect.objectContaining({ id: "prompts.publicationCreate", status: "skipped" }));
    expect(calls("createPrompt")).toHaveLength(0);
  });
  it("cancels an unexpected pending proposal while reporting the broken autoaccept contract", async () => {
    publicationApi({ pending: true });
    await run();
    failed("prompts.publication");
    passed("prompts.publicationWithdraw");
    passed("prompts.publicationCleanup");
    expect(calls("cancelMarketplaceProposal")).toHaveLength(1);
    expect(calls("decideMarketplaceProposal")).toHaveLength(0);
    expect(calls("withdrawMarketplaceEntry")).toHaveLength(0);
  });
  it.each([{ loseSubmission: true }, { wrongSnapshot: true }])(
    "withdraws the automatic publication even after a lost acknowledgement or failed readback: %j",
    async (options) => {
      publicationApi(options);
      await run();
      failed("prompts.publication");
      passed("prompts.publicationWithdraw");
      passed("prompts.publicationCleanup");
      expect(calls("withdrawMarketplaceEntry")).toHaveLength(1);
      expect(calls("decideMarketplaceProposal")).toHaveLength(0);
      const submissions = calls("submitMarketplaceProposal");
      expect(new Set(submissions.map((request) => request.args["Idempotency-Key"])).size).toBe(1);
    },
  );
  it("fails cleanup if the withdrawn proposal's content remains readable", async () => {
    publicationApi({ retainContent: true });
    await run();
    failed("prompts.publicationWithdraw");
    passed("prompts.publicationCleanup");
  });
  it.each([{ failWithdrawal: true }, { foreignPublication: true }])(
    "reports incomplete publication cleanup while still deleting its source: %j",
    async (options) => {
      publicationApi(options);
      await run();
      failed("prompts.publicationWithdraw");
      passed("prompts.publicationCleanup");
      if (options.foreignPublication) expect(calls("withdrawMarketplaceEntry")).toHaveLength(0);
    },
  );
});
