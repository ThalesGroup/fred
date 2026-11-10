// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type {
  MarketplaceProposal,
  Prompt,
  SubmitMarketplaceProposalApiArg,
  WikiPageDetail,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { FRESH } from "../deps/api";
import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";
import type { WeaverChecks } from "./checks";
import { assert, cp, expectAbsent, requireWrite } from "./resourceSupport";

export const teamWiki: Scenario<WeaverChecks> = async (checks, report, signal) => {
  const spaceId = checks.spaceId;
  const fixture: { page?: WikiPageDetail } = {};
  const initialText = "Disposable wiki content.";
  const revisedText = "Revised disposable wiki content.";
  try {
    const created = await runStep(report, "teams.wiki", "Create a disposable team wiki page", async () => {
      await requireWrite(checks, signal);
      const availability = await checks.dispatch(cp.wikiAvailability.initiate({ spaceId }, FRESH)).unwrap();
      if (!availability.enabled) throw new SkipStep("The wiki capability is not available in the disposable team.");
      signal.throwIfAborted();
      const page = await checks
        .dispatch(
          cp.createWikiPage.initiate({
            spaceId,
            createWikiPageRequest: { title: `Self-test ${crypto.randomUUID()}`, content_md: initialText },
          }),
        )
        .unwrap();
      fixture.page = page;
      assert(
        page.revision_id && page.content_md === initialText,
        "The new wiki page has no matching initial revision.",
      );
      return { value: page };
    });
    if (!created) return;
    await runStep(report, "teams.wikiRevision", "Revise the wiki page and verify its history", async () => {
      signal.throwIfAborted();
      const pageArgs = { spaceId, pageId: created.page.page_id };
      const revised = await checks
        .dispatch(
          cp.writeWikiPage.initiate({
            ...pageArgs,
            updateWikiContentRequest: { content_md: revisedText, base_revision_id: created.revision_id },
          }),
        )
        .unwrap();
      assert(
        revised.revision_id && revised.revision_id !== created.revision_id,
        "Editing did not create a new wiki revision.",
      );
      const saved = await checks.dispatch(cp.wikiPage.initiate({ spaceId, pageId: created.page.slug }, FRESH)).unwrap();
      assert(
        saved.page.page_id === created.page.page_id &&
          saved.content_md === revisedText &&
          saved.revision_id === revised.revision_id,
        "The wiki page readback does not match the revised content.",
      );
      const history = await checks.dispatch(cp.wikiRevisions.initiate(pageArgs, FRESH)).unwrap();
      for (const [revision, content, status] of [
        [created.revision_id!, initialText, "superseded"],
        [revised.revision_id, revisedText, "published"],
      ]) {
        assert(
          history.revisions.some((item) => item.revision_id === revision && item.status === status) &&
            history.contents[revision] === content,
          "Wiki history does not preserve the original and current content.",
        );
      }
      return { value: true };
    });
  } finally {
    if (fixture.page) {
      const page = fixture.page.page;
      await runStep(report, "teams.wikiCleanup", "Delete the disposable wiki page", async () => {
        await checks.dispatch(cp.deleteWikiPage.initiate({ spaceId, pageId: page.page_id })).unwrap();
        await expectAbsent(() => checks.dispatch(cp.wikiPage.initiate({ spaceId, pageId: page.slug }, FRESH)).unwrap());
        const tree = await checks.dispatch(cp.wikiPages.initiate({ spaceId }, FRESH)).unwrap();
        assert(!tree.pages.some((item) => item.page_id === page.page_id), "The deleted wiki page remains listed.");
        return { value: true };
      });
    }
  }
};

export const promptPublication: Scenario<WeaverChecks> = async (checks, report, signal) => {
  const spaceId = checks.spaceId;
  const marketplaceSpaceId = checks.organizationId;
  const fixture: { prompt?: Prompt; submission?: SubmitMarketplaceProposalApiArg; proposal?: MarketplaceProposal } = {};
  try {
    const prompt = await runStep(
      report,
      "prompts.publicationCreate",
      "Create a disposable prompt for publication",
      async () => {
        await requireWrite(checks, signal);
        if (marketplaceSpaceId !== spaceId) await requireWrite({ ...checks, spaceId: marketplaceSpaceId }, signal);
        signal.throwIfAborted();
        const created = await checks
          .dispatch(
            cp.createPrompt.initiate({
              spaceId,
              createPromptRequest: {
                logical_name: `selftest-publication-${crypto.randomUUID()}`,
                display_name: "Self-test publication",
                text: "Disposable published prompt content.",
              },
            }),
          )
          .unwrap();
        fixture.prompt = created;
        assert(created.space_id === spaceId, "The publication source is not in the selected space.");
        return { value: created };
      },
    );
    if (!prompt) return;
    await runStep(report, "prompts.publication", "Publish a prompt and verify its marketplace snapshot", async () => {
      signal.throwIfAborted();
      fixture.submission = {
        marketplaceSpaceId,
        "Idempotency-Key": crypto.randomUUID(),
        submitProposalRequest: {
          kind: "prompt",
          source_space_id: spaceId,
          source_resource_id: prompt.prompt_id,
          expected_revision: prompt.updated_at,
        },
      };
      const proposal = await checks.dispatch(cp.submitMarketplaceProposal.initiate(fixture.submission)).unwrap();
      fixture.proposal = proposal;
      assert(
        proposal.marketplace_space_id === marketplaceSpaceId &&
          proposal.proposing_space_id === spaceId &&
          proposal.submitted_by === checks.userId &&
          proposal.package.kind === "prompt" &&
          proposal.package.content.logical_name === prompt.logical_name &&
          proposal.package.content.text === prompt.text,
        "The proposal does not contain the disposable prompt in its intended marketplace.",
      );
      assert(
        proposal.state === "pending" && proposal.actions.can_decide,
        "The new prompt proposal is not awaiting an authorized decision.",
      );
      signal.throwIfAborted();
      const decision = await checks
        .dispatch(
          cp.decideMarketplaceProposal.initiate({
            marketplaceSpaceId,
            proposalId: proposal.proposal_id,
            proposalDecisionRequest: { approve: true, expected_publication_version: proposal.publication_version },
          }),
        )
        .unwrap();
      assert(
        decision.state === "approved" && decision.published_proposal_id === proposal.proposal_id,
        "The prompt proposal was not published.",
      );
      const entry = await checks
        .dispatch(cp.marketplaceEntry.initiate({ marketplaceSpaceId, entryId: proposal.entry_id }, FRESH))
        .unwrap();
      assert(
        entry.proposal_id === proposal.proposal_id &&
          entry.publication_version === decision.publication_version &&
          entry.package.kind === "prompt" &&
          entry.package.content.logical_name === prompt.logical_name &&
          entry.package.content.text === prompt.text,
        "The published marketplace snapshot does not match the disposable prompt.",
      );
      return { value: true };
    });
  } finally {
    if (fixture.submission) {
      const submission = fixture.submission;
      await runStep(
        report,
        "prompts.publicationWithdraw",
        "Withdraw publication or cancel its pending proposal",
        async () => {
          // Replay the same idempotent request if the submission acknowledgement was lost.
          const proposal =
            fixture.proposal ?? (await checks.dispatch(cp.submitMarketplaceProposal.initiate(submission)).unwrap());
          const args = { marketplaceSpaceId, proposalId: proposal.proposal_id };
          const current = await checks.dispatch(cp.marketplaceProposal.initiate(args, FRESH)).unwrap();
          assert(
            current.proposal_id === proposal.proposal_id &&
              current.entry_id === proposal.entry_id &&
              current.marketplace_space_id === marketplaceSpaceId &&
              current.proposing_space_id === spaceId &&
              current.submitted_by === checks.userId &&
              current.package.kind === "prompt" &&
              current.package.content.logical_name === fixture.prompt?.logical_name,
            "The proposal no longer matches the disposable publication.",
          );
          if (current.state === "pending") {
            const cancelled = await checks.dispatch(cp.cancelMarketplaceProposal.initiate(args)).unwrap();
            assert(cancelled.state === "cancelled", "The pending prompt proposal was not cancelled.");
          }
          const entryArgs = { marketplaceSpaceId, entryId: proposal.entry_id };
          if (current.published_proposal_id) {
            assert(
              current.published_proposal_id === proposal.proposal_id,
              "Another proposal now owns this publication; it was left unchanged.",
            );
            await checks
              .dispatch(
                cp.withdrawMarketplaceEntry.initiate({
                  ...entryArgs,
                  withdrawRequest: { expected_publication_version: current.publication_version },
                }),
              )
              .unwrap();
          }
          await expectAbsent(() => checks.dispatch(cp.marketplaceEntry.initiate(entryArgs, FRESH)).unwrap());
          return {
            value: true,
            detail: "No published test entry remains. Proposal history is retained by the marketplace.",
          };
        },
      );
    }
    if (fixture.prompt) {
      const args = { spaceId, promptId: fixture.prompt.prompt_id };
      await runStep(report, "prompts.publicationCleanup", "Delete the publication's source prompt", async () => {
        await checks.dispatch(cp.deletePrompt.initiate(args)).unwrap();
        await expectAbsent(() => checks.dispatch(cp.getPrompt.initiate(args, FRESH)).unwrap());
        return { value: true };
      });
    }
  }
};
