// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import Chip from "@shared/atoms/Chip/Chip";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import { TOOL_PACK_SECTIONS } from "../TeamAgentsPage/AgentFormModal/toolPacks";
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
  const { capabilities, role, usage_statement, tuning_field_values } = value.content;
  const instructions: unknown = tuning_field_values["prompts.system"];
  const capabilityLabels = TOOL_PACK_SECTIONS.flatMap((section) => section.packs.flatMap((pack) => pack.includes));
  const exportedCapabilities = Object.entries(capabilities).map(([id, capability]) => ({
    id,
    label: t(capabilityLabels.find((item) => item.capabilityId === id)?.labelKey ?? `capability.${id}.name`, {
      defaultValue: id,
    }),
    files: Object.entries(capability.files),
  }));
  return (
    <div className={styles.content}>
      {role && (
        <section>
          <h3>{t("rework.teams.formAgent.fields.role.label")}</h3>
          <p className={styles.text}>{role}</p>
        </section>
      )}
      {usage_statement && (
        <section>
          <h3>{t("rework.teams.formAgent.fields.usageStatement.label")}</h3>
          <p className={styles.text}>{usage_statement}</p>
        </section>
      )}
      <section>
        <h3>{t("rework.localMarketplace.instructions")}</h3>
        {typeof instructions === "string" && instructions.trim() ? (
          <pre className={styles.text} tabIndex={0}>
            {instructions}
          </pre>
        ) : (
          <p className={styles.identity}>{t("rework.localMarketplace.noInstructions")}</p>
        )}
      </section>
      <section>
        <h3>{t("rework.localMarketplace.capabilities")}</h3>
        {Object.keys(capabilities).length ? (
          <div className={styles.actions}>
            {exportedCapabilities.map(({ id, label }) => (
              <Chip key={id} label={label} />
            ))}
          </div>
        ) : (
          <p className={styles.identity}>{t("rework.localMarketplace.noCapabilities")}</p>
        )}
      </section>
      {exportedCapabilities.map(({ id, label, files }) =>
        files.length ? (
          <Disclosure key={id} title={t("rework.localMarketplace.files", { capability: label })}>
            <ul>
              {files.map(([path, encoded]) => (
                <li key={path}>
                  <a download={path.split("/").pop()} href={`data:application/octet-stream;base64,${encoded}`}>
                    {path}
                  </a>
                </li>
              ))}
            </ul>
          </Disclosure>
        ) : null,
      )}
    </div>
  );
}
