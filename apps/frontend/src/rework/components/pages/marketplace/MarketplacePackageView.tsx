// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import type { MarketplacePackage } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./Marketplace.module.css";

/** Render the returned snapshot as text; never execute submitted markdown or configuration. */
export default function MarketplacePackageView({ value }: { value: MarketplacePackage }) {
  const { t } = useTranslation();
  if (value.kind === "prompt")
    return (
      <section>
        <p>
          {value.content.logical_name} · {value.content.tags.join(", ")}
        </p>
        <pre className={styles.text} tabIndex={0}>
          {value.content.text}
        </pre>
      </section>
    );
  if (value.kind === "skill")
    return (
      <section>
        {Object.entries(value.content.files).map(([path, text]) => (
          <details key={path}>
            <summary>{path}</summary>
            <pre className={styles.text} tabIndex={0}>
              {text}
            </pre>
          </details>
        ))}
      </section>
    );
  const { capabilities, ...configuration } = value.content;
  return (
    <section>
      <h3>{t("rework.localMarketplace.configuration")}</h3>
      <pre className={styles.text} tabIndex={0}>
        {JSON.stringify(configuration, null, 2)}
      </pre>
      {Object.entries(capabilities).map(([id, capability]) => (
        <details key={id}>
          <summary>{id}</summary>
          <pre className={styles.text} tabIndex={0}>
            {JSON.stringify({ schema_version: capability.schema_version, config: capability.config }, null, 2)}
          </pre>
          {Object.entries(capability.files).map(([path, encoded]) => (
            <details key={path}>
              <summary>{path}</summary>
              <a download={path.split("/").pop()} href={`data:application/octet-stream;base64,${encoded}`}>
                {t("rework.localMarketplace.downloadFile")}
              </a>
            </details>
          ))}
        </details>
      ))}
    </section>
  );
}
