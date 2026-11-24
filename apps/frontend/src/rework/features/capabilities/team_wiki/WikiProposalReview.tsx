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

// The approval card's wiki half (WIKI-04): what an agent is asking to write.
//
// The gate hands us a tool name and a truncated argument preview. That preview
// holds the proposal id — short by design, which is exactly why the write is
// two steps — and the proposal itself is fetched here, with the text it would
// replace, so the person deciding sees the change rather than an id. Their
// choice submits or deletes the draft with their own token before the run
// resumes; the tool then only reads what became of it.

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { useParams } from "react-router-dom";
import { resolveAgentSpace } from "../../../components/pages/TeamAgentsPage/weaverAgents";
import { useMySpacesQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  useSubmitWikiProposalMutation,
  useWikiProposalQuery,
  useWithdrawWikiProposalMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { errorText } from "@rework/features/teamWiki/wikiErrors";
import { diffStat, lineDiff } from "@rework/features/teamWiki/lineDiff";
import type { CapabilityHitlRendererProps } from "../types";
import styles from "./WikiProposalReview.module.css";

/** The proposal id out of the gate's argument preview.
 *
 * The preview is the tool call's arguments rendered as text and cut at 1 200
 * characters. `wiki_submit_proposal` takes one short id, so it always
 * survives the cut — the whole reason submitting is its own call. */
function proposalIdFrom(preview: string | undefined): string | null {
  if (!preview) return null;
  const match = /"?proposal_id"?\s*[:=]\s*"?([A-Za-z0-9_-]+)"?/.exec(preview);
  return match ? match[1] : null;
}

export function WikiProposalReview({ call, onDecide }: CapabilityHitlRendererProps) {
  const { t } = useTranslation();
  const { teamId } = useParams<{ teamId: string }>();
  const memberships = useMySpacesQuery();
  const spaceId = resolveAgentSpace(memberships.currentData, teamId)?.id;
  const [open, setOpen] = useState(false);
  const proposalId = proposalIdFrom(call.args_preview);

  const { data: proposal, isFetching } = useWikiProposalQuery(
    { spaceId: spaceId ?? "", proposalId: proposalId ?? "" },
    { skip: !spaceId || !proposalId, refetchOnMountOrArgChange: true },
  );
  const [submit] = useSubmitWikiProposalMutation();
  const [withdraw] = useWithdrawWikiProposalMutation();
  const [failure, setFailure] = useState<string | null>(null);
  const status = proposal?.status;

  useEffect(() => {
    if (!onDecide || !spaceId || !proposalId) return;
    onDecide(async (choiceId) => {
      setFailure(null);
      try {
        // Already submitted when an earlier resume never reached the run.
        if (choiceId === "proceed" && status !== "pending" && status !== "published")
          await submit({ spaceId, proposalId }).unwrap();
        if (choiceId === "cancel") await withdraw({ spaceId, proposalId }).unwrap();
        return true;
      } catch (error) {
        const code = (error as { status?: number } | undefined)?.status;
        // Declining a proposal that no longer exists leaves nothing to undo.
        if (choiceId === "cancel" && code === 404) return true;
        setFailure(code === 409 ? t("rework.wiki.proposal.outdated") : errorText(error));
        return false;
      }
    });
    return () => onDecide(undefined);
  }, [onDecide, spaceId, proposalId, status, submit, withdraw, t]);

  // One pass, on render rather than on open: the summary line needs the
  // added/removed counts before anyone opens anything. What keeps that
  // affordable is `MAX_DIFF_CELLS`, not laziness — see lineDiff.ts.
  const lines = useMemo(
    () => (proposal ? lineDiff(proposal.current_content_md ?? "", proposal.content_md) : []),
    [proposal],
  );
  const stat = useMemo(() => diffStat(lines), [lines]);

  // No id in the preview, or the proposal is gone: the accept/reject buttons
  // still work, so say nothing rather than blocking the decision on a detail.
  if (!proposalId) return null;

  return (
    <div className={styles.review}>
      <span className={styles.summary}>
        {isFetching && !proposal ? (
          <Spinner size={16} />
        ) : proposal ? (
          t(
            `rework.wiki.proposal.${proposal.kind === "page" ? "newPage" : proposal.kind === "file" ? "file" : "edit"}`,
            {
              title: proposal.title,
              added: stat.added,
              removed: stat.removed,
            },
          )
        ) : (
          t("rework.wiki.proposal.unavailable")
        )}
      </span>
      {(status === "pending" || status === "published") && (
        <span className={styles.summary} role="status">
          {t(status === "published" ? "rework.wiki.proposal.published" : "rework.wiki.proposal.submitted")}
        </span>
      )}
      {failure && (
        <span className={styles.summary} role="alert">
          {failure}
        </span>
      )}
      {proposal && proposal.kind !== "file" && (
        <Button color="primary" variant="text" size="small" onClick={() => setOpen(true)}>
          {t("rework.wiki.proposal.seeChanges")}
        </Button>
      )}

      <Dialog
        open={open}
        title={t("rework.wiki.proposal.dialogTitle", { title: proposal?.title ?? "" })}
        confirmLabel={t("rework.wiki.proposal.close")}
        hideCancel
        maxWidth={860}
        onConfirm={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      >
        {/* Read-only on purpose: approving is one decision on the whole change
            (RFC §8.2). Amending in the modal needs an editor and a call on who
            is then the author — deferred, not forgotten. */}
        <pre className={styles.diff}>
          {lines.map((line, index) => (
            <span key={index} className={styles[line.op]}>
              {line.op === "added" ? "+ " : line.op === "removed" ? "- " : "  "}
              {line.text || " "}
              {"\n"}
            </span>
          ))}
        </pre>
      </Dialog>
    </div>
  );
}
