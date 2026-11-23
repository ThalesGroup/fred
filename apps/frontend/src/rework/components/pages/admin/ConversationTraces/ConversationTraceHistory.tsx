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

import { useState } from "react";
import { skipToken } from "@reduxjs/toolkit/query";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { useGetConversationTraceHistoryQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { ConversationTraceTurn } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TRACE_TRANSLATION_PREFIX } from "./traceControls";
import styles from "./ConversationTraces.module.css";

export function ConversationTraceHistory({ sessionId, turn }: { sessionId: string; turn: ConversationTraceTurn }) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const [open, setOpen] = useState(false);
  const [pages, setPages] = useState<(number | undefined)[]>([undefined]);
  const canRead = turn.access === "shared" || turn.access === "local";
  const history = useGetConversationTraceHistoryQuery(
    open && canRead ? { sessionId, exchangeId: turn.exchange_id, afterRank: pages[pages.length - 1] } : skipToken,
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  const evidence = history.currentData;

  return (
    <section className={styles.history} aria-label={t("savedHistory")}>
      <h3>{t("savedHistory")}</h3>
      {!canRead ? (
        <p>{t("historyMasked")}</p>
      ) : (
        <>
          <Button
            color="secondary"
            size="small"
            variant="outlined"
            aria-expanded={open}
            onClick={() => {
              setPages([undefined]);
              setOpen(!open);
            }}
          >
            {t(open ? "hideHistory" : "viewHistory")}
          </Button>
          {open &&
            (history.isError ? (
              <p role="alert">
                {t("status" in history.error && history.error.status === 403 ? "historyMasked" : "historyUnavailable")}
              </p>
            ) : !evidence ? (
              <p role="status">{t("historyLoading")}</p>
            ) : !evidence.available ? (
              <p>{t("historyUnavailable")}</p>
            ) : (
              <>
                <ol className={styles.historyMessages}>
                  {evidence.messages.map((message) => (
                    <li key={message.rank}>
                      <details open>
                        <summary>
                          {t(
                            `historyRoles.${
                              message.channel === "tool_call" || message.channel === "tool_result"
                                ? message.channel
                                : message.role
                            }`,
                          )}
                        </summary>
                        {message.parts.map((part, index) =>
                          part.type === "text" ? (
                            <p key={index} className={styles.historyText}>
                              {part.text}
                            </p>
                          ) : (
                            <pre key={index}>{JSON.stringify(part, null, 2)}</pre>
                          ),
                        )}
                      </details>
                    </li>
                  ))}
                </ol>
                {(pages.length > 1 || evidence.next_rank != null) && (
                  <div className={styles.historyPaging}>
                    <Button
                      color="secondary"
                      size="small"
                      variant="outlined"
                      disabled={pages.length === 1 || history.isFetching}
                      onClick={() => setPages(pages.slice(0, -1))}
                    >
                      {t("previous")}
                    </Button>
                    <Button
                      color="secondary"
                      size="small"
                      variant="outlined"
                      disabled={evidence.next_rank == null || history.isFetching}
                      onClick={() => setPages([...pages, evidence.next_rank ?? undefined])}
                    >
                      {t("next")}
                    </Button>
                  </div>
                )}
              </>
            ))}
        </>
      )}
    </section>
  );
}
