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
import { useTranslation } from "react-i18next";
import NavPanelHeader from "@shared/molecules/NavPanelHeader/NavPanelHeader";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import TeamSelectionListItem from "@shared/molecules/TeamSelectionListItem/TeamSelectionListItem";
import { useMySpacesQuery } from "../../../../../../slices/fredManager/fredManagerApiEnhancements";
import styles from "./HomeNavPanel.module.scss";

export default function HomeNavPanel() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const spaces = useMySpacesQuery();
  const byId = new Map(spaces.data?.map((space) => [space.id, space.name]));
  const ordered = spaces.isError
    ? []
    : [...(spaces.data ?? [])].sort((a, b) =>
        a.path
          .map((id) => byId.get(id) ?? id)
          .join(" / ")
          .localeCompare(b.path.map((id) => byId.get(id) ?? id).join(" / ")),
      );
  return (
    <div className={styles.panel}>
      <NavPanelHeader title={t("rework.manager.spaces")} />
      <div className={styles.teamSort}>
        <SearchInput
          size="xs"
          value={search}
          onChange={setSearch}
          placeholder={t("rework.manager.search")}
          ariaLabel={t("rework.manager.search")}
          clearAriaLabel={t("rework.home.searchClear")}
        />
      </div>
      <div className={styles.scroll}>
        {ordered
          .filter((space) => space.name.toLowerCase().includes(search.trim().toLowerCase()))
          .map((space) => (
            <div key={space.id} className={styles[space.kind]}>
              <TeamSelectionListItem
                redirection={{ pathname: "/home", search: `?space=${space.id}` }}
                name={space.name}
                avatarName={space.name}
                description={[
                  t(`rework.manager.kinds.${space.kind}`),
                  ...space.roles.map((role) => t(`rework.manager.roles.${role}`)),
                ].join(" / ")}
              />
            </div>
          ))}
      </div>
    </div>
  );
}
