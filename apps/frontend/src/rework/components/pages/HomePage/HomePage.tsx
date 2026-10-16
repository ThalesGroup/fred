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

import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { useMySpacesQuery } from "../../../../slices/fredManager/fredManagerApiEnhancements";
import styles from "./HomePage.module.scss";

// Kept for the unmounted activity widgets; the home journey does not query them.
export type HomePeriod = 7 | 30 | 90;

export default function HomePage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const spaces = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const firstName = KeyCloakService.GetUserGivenName() || undefined;
  const selected = params.get("space") ?? spaces.data?.find((space) => space.kind === "organization")?.id;
  const visible = (spaces.data ?? []).filter((space) => selected === undefined || space.id === selected);
  const byId = new Map(
    spaces.data?.map((space) => [space.id, space.personal_owner ? t("rework.sidebar.team.userTeam") : space.name]),
  );
  return (
    <div className={styles.page}>
      <header className={styles.headerText}>
        <h1 className={styles.title}>
          {firstName ? t("rework.home.greetingNamed", { name: firstName }) : t("rework.home.greeting")}
        </h1>
        <h2 className={styles.subtitle}>{t("rework.manager.spaces")}</h2>
      </header>
      {spaces.isLoading ? (
        <p role="status">{t("common.loading")}</p>
      ) : spaces.isError ? (
        <div role="alert">
          <p>{t("rework.manager.unavailable")}</p>
          <Button color="primary" variant="outlined" size="medium" onClick={() => void spaces.refetch()}>
            {t("rework.provisioning.retryAuthority")}
          </Button>
        </div>
      ) : visible.length === 0 ? (
        <p>{t(selected !== undefined ? "rework.manager.missingSpace" : "rework.manager.empty")}</p>
      ) : (
        visible.map((space) => (
          <section key={space.id} className={styles.membership} aria-label={byId.get(space.id)}>
            <h2>{byId.get(space.id)}</h2>
            <dl>
              <dt>{t("rework.manager.kind")}</dt>
              <dd>{t(`rework.manager.kinds.${space.kind}`)}</dd>
              <dt>{t("rework.manager.hierarchy")}</dt>
              <dd>{space.path.map((id) => byId.get(id) ?? id).join(" / ")}</dd>
              <dt>{t("rework.manager.roleLabel")}</dt>
              <dd>{space.roles.map((role) => t(`rework.manager.roles.${role}`)).join(", ")}</dd>
            </dl>
          </section>
        ))
      )}
    </div>
  );
}
