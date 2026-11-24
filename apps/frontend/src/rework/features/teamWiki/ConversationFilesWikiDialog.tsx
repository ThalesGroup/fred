// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import {
  useWikiAvailabilityQuery,
  useWikiPagesQuery,
  useProposeWikiFileMutation,
} from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { ProposeWikiFileRequest, WikiProposal } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { WikiDestinationPicker } from "./WikiDestinationPicker";
import { sha256, type WikiShareFile } from "./wikiFileShare";
import { ancestorsOf, MAX_PAGE_DEPTH, moveTargets } from "./wikiTree";
import styles from "./ConversationFilesWikiDialog.module.css";

type Attempt = { key: string; body: ProposeWikiFileRequest };
type Outcome = { result?: WikiProposal; error?: string };
const definiteFailure = (status?: number, code?: string) =>
  ["upload_failed", "upload_expired", "content_changed", "quota_exceeded"].includes(code ?? "") ||
  [404, 422, 413].includes(status ?? 0);

/** One gesture, independent durable Wiki receipts. Retry never resends a known success. */
export function ConversationFilesWikiDialog({
  sessionId,
  spaceId,
  spaceName,
  wikiUrl,
  files,
  onClose,
}: {
  sessionId: string;
  spaceId: string;
  spaceName: string;
  wikiUrl: string;
  files: WikiShareFile[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const label = (key: string) => t(`chatbot.sessionAttachments.share.${key}`);
  const availability = useWikiAvailabilityQuery({ spaceId, sessionId }, { refetchOnMountOrArgChange: true });
  const pages = useWikiPagesQuery({ spaceId, sessionId }, { refetchOnMountOrArgChange: true });
  const [propose] = useProposeWikiFileMutation();
  const [destination, setDestination] = useState("");
  const [newPage, setNewPage] = useState(false);
  const [pageTitle, setPageTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});
  const inFlight = useRef(false);
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const destinations = moveTargets(pages.currentData?.pages ?? []);
  useEffect(() => {
    if (pages.currentData && !pages.isFetching && availability.currentData?.can_publish && !destinations.length) {
      setNewPage(true);
    }
  }, [pages.currentData, pages.isFetching, availability.currentData?.can_publish, destinations.length]);
  const problem = availability.error || pages.error || (availability.currentData && !availability.currentData.enabled);
  const allowed =
    !problem &&
    (newPage
      ? availability.currentData?.can_publish &&
        pageTitle.trim().length > 0 &&
        (!destination || ancestorsOf(pages.currentData?.pages ?? [], destination).length + 2 <= MAX_PAGE_DEPTH)
      : destinations.some(({ page }) => page.slug === destination));
  const complete = files.every((file) => outcomes[file.key]?.result);
  const submit = async () => {
    if (!allowed || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setStarted(true);
    for (const file of files) {
      if (!live.current) break;
      if (outcomes[file.key]?.result) continue;
      let slot: string | undefined;
      try {
        // Persist metadata only, never file bytes. A lost response or dialog reopen
        // replays the exact attempt, even if the original has since changed.
        const tree = pages.currentData?.pages ?? [];
        const parent = tree.find((page) => page.slug === destination);
        const trail = parent ? [...ancestorsOf(tree, destination), parent].map((page) => page.title) : [];
        if (newPage) trail.push(pageTitle.trim().normalize("NFC"));
        // Creating a named page and selecting that same page after a lost response
        // identify the same destination. Keep the original request for the replay.
        slot = `wiki-share:${await sha256(new TextEncoder().encode(JSON.stringify([spaceId, sessionId, file.key, trail])))}`;
        const previous = sessionStorage.getItem(slot);
        let attempt: Attempt;
        if (previous) attempt = JSON.parse(previous) as Attempt;
        else {
          const source = await file.prepareWikiShare();
          if (!live.current) break;
          attempt = {
            key: crypto.randomUUID(),
            body: {
              ...source,
              parent_slug: destination || undefined,
              destination_title: newPage ? pageTitle.trim() : undefined,
            },
          };
          sessionStorage.setItem(slot, JSON.stringify(attempt));
        }
        if (!live.current) break;
        const result = await propose({
          spaceId,
          sessionId,
          "Idempotency-Key": attempt.key,
          proposeWikiFileRequest: attempt.body,
        }).unwrap();
        if (live.current) setOutcomes((previous) => ({ ...previous, [file.key]: { result } }));
      } catch (error) {
        const response = error as { status?: number; data?: { code?: string } };
        const code = response.data?.code;
        if (slot && definiteFailure(response.status, code)) sessionStorage.removeItem(slot);
        const message =
          code === "content_changed"
            ? "changed"
            : code === "quota_exceeded"
              ? "quota"
              : code === "save_failed"
                ? "saveFailed"
                : code === "save_pending"
                  ? "saving"
                  : "error";
        if (live.current) setOutcomes((previous) => ({ ...previous, [file.key]: { error: label(message) } }));
      }
    }
    inFlight.current = false;
    if (live.current) {
      setBusy(false);
      void pages.refetch();
    }
  };
  return (
    <Dialog
      open
      title={label("action")}
      maxWidth={640}
      busy={busy}
      hideCancel={complete}
      confirmLabel={
        complete
          ? t("common.close")
          : started
            ? t("common.retry")
            : label(availability.currentData?.can_publish ? "publish" : "submit")
      }
      confirmDisabled={!complete && (!allowed || availability.isFetching || pages.isFetching)}
      onConfirm={() => {
        if (complete) onClose();
        else void submit();
      }}
      onCancel={onClose}
    >
      <div className={styles.content}>
        <p>
          {spaceName} · {label("audience")}
        </p>
        <ul className={styles.files}>
          {files.map((file) => {
            const outcome = outcomes[file.key];
            return (
              <li key={file.key}>
                <span className={styles.name}>{file.name}</span>
                {outcome?.error && <span role="alert">{outcome.error}</span>}
                {outcome?.result && (
                  <span role="status">
                    {label(outcome.result.status === "published" ? "published" : "pending")}
                    {outcome.result.status === "published" && outcome.result.slug && (
                      <>
                        {" "}
                        · <Link to={`${wikiUrl}/${encodeURIComponent(outcome.result.slug)}`}>{label("openFile")}</Link>
                      </>
                    )}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
        {!complete && (
          <>
            {problem && (
              <p role="alert">
                {label("unavailable")}{" "}
                <Button
                  size="small"
                  variant="text"
                  color="primary"
                  onClick={() => {
                    void availability.refetch();
                    void pages.refetch();
                  }}
                >
                  {t("common.retry")}
                </Button>
              </p>
            )}
            {destinations.length > 0 && <p>{label("destination")}</p>}
            <WikiDestinationPicker
              pages={pages.currentData?.pages ?? []}
              value={destination}
              onChange={setDestination}
              disabled={busy || started}
              levelsBelow={newPage ? 2 : 1}
            />
            {!destinations.length && !pages.isFetching && !problem && !availability.currentData?.can_publish && (
              <p>
                {label("noPages")} <Link to={wikiUrl}>{label("openWiki")}</Link>
              </p>
            )}
            {availability.currentData?.can_publish && destinations.length > 0 && (
              <Button
                size="small"
                variant="text"
                color="primary"
                icon={{ category: "outlined", type: "add" }}
                disabled={busy || started}
                onClick={() => setNewPage(!newPage)}
              >
                {label(newPage ? "existingPage" : "newPage")}
              </Button>
            )}
            {newPage && (
              <>
                <TextInput
                  label={label("pageName")}
                  value={pageTitle}
                  onChange={(event) => setPageTitle(event.target.value)}
                  disabled={busy || started}
                  compact
                />
                <p>
                  {label("under")} {destinations.find(({ page }) => page.slug === destination)?.path ?? spaceName}
                  {destination && (
                    <Button
                      size="small"
                      color="primary"
                      variant="text"
                      disabled={busy || started}
                      onClick={() => setDestination("")}
                    >
                      {label("atRoot")}
                    </Button>
                  )}
                </p>
              </>
            )}
            <p className={styles.hint}>{label("copy")}</p>
          </>
        )}
      </div>
    </Dialog>
  );
}
