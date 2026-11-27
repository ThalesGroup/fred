/* Copyright Thales 2026
 * SPDX-License-Identifier: Apache-2.0
 */

import { useTranslation } from "react-i18next";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { GetConversationTraceMaskedEvidenceApiArg } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ConversationTraces.module.css";
import TraceJson from "./TraceJson";
import { TRACE_TRANSLATION_PREFIX } from "./traceControls";

export function MaskedTracePayload({
  label,
  ...request
}: GetConversationTraceMaskedEvidenceApiArg & { label?: string }) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX + ".masking" });
  const query = enhancedControlPlaneApi.useGetConversationTraceMaskedEvidenceQuery(request, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
  });
  if (query.isFetching || query.isLoading) return <p role="status">{t("loading")}</p>;
  const documents = Object.entries(query.currentData?.documents ?? {});
  if (query.isError || !documents.length) return <p>{t("unavailable")}</p>;

  return (
    <div className={styles.httpContent}>
      <p className={styles.help}>{t(request.kind === "http" ? "diagnosticJson" : "description")}</p>
      {documents.map(([key, document]) => {
        const title = label ?? t("documents." + key);
        return (
          <section className={styles.httpPayload} key={key} aria-label={title}>
            <h4>{title}</h4>
            {document.unavailable ? (
              <p>{t("unavailable")}</p>
            ) : (
              <TraceJson
                code={JSON.stringify(document.data, null, 2)}
                label={title}
                annotations={document.annotations}
                modelRequest={request.kind === "http" && key === "request"}
              />
            )}
          </section>
        );
      })}
    </div>
  );
}
