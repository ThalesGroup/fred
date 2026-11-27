/* Copyright Thales 2026
 * SPDX-License-Identifier: Apache-2.0
 */

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { GetConversationTraceMaskedEvidenceApiArg } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ConversationTraces.module.css";
import TraceJson from "./TraceJson";
import { TRACE_TRANSLATION_PREFIX } from "./traceControls";

export function MaskedTracePayload({
  label,
  renderHttpRequestAction,
  ...request
}: GetConversationTraceMaskedEvidenceApiArg & {
  label?: string;
  renderHttpRequestAction?: (body: string) => ReactNode;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const query = enhancedControlPlaneApi.useGetConversationTraceMaskedEvidenceQuery(request, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
  });
  if (query.isFetching || query.isLoading) return <p role="status">{t("masking.loading")}</p>;
  const documents = Object.entries(query.currentData?.documents ?? {});
  if (query.isError || !documents.length) return <p>{t("masking.unavailable")}</p>;

  return (
    <div className={styles.httpContent}>
      <p className={styles.help}>{t(request.kind === "http" ? "masking.diagnosticJson" : "masking.description")}</p>
      {documents.map(([key, document]) => {
        const title = label ?? t("masking.documents." + key);
        const body = document.data;
        const code = JSON.stringify(body, null, 2);
        const httpRequest = request.kind === "http" && key === "request";
        const action =
          httpRequest && !document.unavailable && body && typeof body === "object" && !Array.isArray(body)
            ? renderHttpRequestAction?.(code)
            : undefined;
        return (
          <section className={styles.httpPayload} key={key} aria-label={title}>
            <header>
              <h4>{title}</h4>
              {action}
            </header>
            {action && <p>{t("http.replay.maskedSetup")}</p>}
            {document.unavailable ? (
              <p>{t("masking.unavailable")}</p>
            ) : (
              <TraceJson
                code={code}
                label={title}
                annotations={document.annotations}
                modelRequest={request.kind === "model" && key === "model" ? "input" : httpRequest}
              />
            )}
          </section>
        );
      })}
    </div>
  );
}
