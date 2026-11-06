// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSelfTestAccess } from "@core/hooks/useSelfTestAccess";
import Select from "@shared/molecules/Select/Select";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { useMySpacesQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { MySpace } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useApiDispatch, useApiRead } from "../../../../features/pipeline/deps/api";
import { bindRunDispatch } from "../../../../features/pipeline/weaver/checks";
import { useWeaverFamilies } from "../../../../features/pipeline/weaver/useWeaverFamilies";
import { SelfTestView } from "./SelfTestView";
import { WeaverManualTests } from "./WeaverManualTests";

export default function WeaverSelfTestPage() {
  const access = useSelfTestAccess();
  if (access.loading) return null;
  if (!access.allowed || !access.userId) return <Navigate to="/unauthorized" replace />;
  return <SpaceSelection key={access.userId} userId={access.userId} />;
}

function SpaceSelection({ userId }: { userId: string }) {
  const spaces = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const available = spaces.isError ? [] : (spaces.currentData ?? []);
  const fallback =
    available.find((space) => space.kind === "team" && space.roles.includes("editor")) ??
    available.find((space) => space.kind === "personal" && space.roles.includes("editor"));
  const [choice, setChoice] = useState<string>(() => fallback?.id);
  useEffect(() => {
    if (choice === undefined && fallback) setChoice(fallback.id);
  }, [choice, fallback]);
  const selected = available.find((space) => space.id === (choice ?? fallback?.id));
  const path = spacePath(selected, available);
  return (
    <Runs
      key={JSON.stringify(path.map(({ id, kind, organization_id }) => [id, kind, organization_id]))}
      userId={userId}
      path={path}
      spaces={available}
      onSelect={setChoice}
      scopeError={spaces.isError}
    />
  );
}

function linked(parent: MySpace, child: MySpace) {
  return (
    child.parent_id === parent.id &&
    child.organization_id === parent.organization_id &&
    ((parent.kind === "organization" && child.kind === "team") || (parent.kind === "team" && child.kind === "project"))
  );
}

function spacePath(selected: MySpace | undefined, spaces: MySpace[]): MySpace[] {
  if (!selected) return [];
  const parent = spaces.find((space) => linked(space, selected));
  return parent ? [...spacePath(parent, spaces), selected] : [selected];
}

function Runs({
  userId,
  path,
  spaces,
  onSelect,
  scopeError,
}: {
  userId: string;
  path: MySpace[];
  spaces: MySpace[];
  onSelect: (id: string) => void;
  scopeError: boolean;
}) {
  const { t } = useTranslation();
  const dispatch = useApiDispatch();
  const runDispatch = useMemo(() => bindRunDispatch(dispatch), [dispatch]);
  const read = useApiRead(runDispatch);
  const selected = path[path.length - 1];
  const campaignTeam = path.find((space) => space.kind === "team");
  const context = useMemo(
    () => ({
      userId,
      dispatch: runDispatch,
      read,
      spaceId: selected?.id ?? "",
      spaceKind: selected?.kind,
      organizationId: selected?.organization_id ?? "",
    }),
    [userId, runDispatch, read, selected],
  );
  const levelContext = (kind: MySpace["kind"]) => {
    const space = path.find((item) => item.kind === kind);
    return {
      ...context,
      spaceId: space?.id ?? "",
      spaceKind: space?.kind,
      organizationId: space?.organization_id ?? "",
    };
  };
  const shared = useWeaverFamilies(context, "shared");
  const organization = useWeaverFamilies(levelContext("organization"), "organization");
  const team = useWeaverFamilies(levelContext("team"), "team");
  const project = useWeaverFamilies(levelContext("project"), "project");
  const personal = useWeaverFamilies(levelContext("personal"), "personal");
  const byKind = { organization, team, project, personal };
  const label = (space: MySpace) => `${t(`rework.selftest.path.${space.kind}`)}: ${space.name}`;
  const groups = [
    { id: "shared", title: t("rework.selftest.path.shared"), families: shared },
    ...path.map((space, index) => ({
      id: space.id,
      title: path
        .slice(0, index + 1)
        .map(label)
        .join(" / "),
      families: byKind[space.kind],
    })),
  ];
  const roots = spaces.filter((space) => !spaces.some((parent) => linked(parent, space)));
  const options = (items: MySpace[]) => items.map((space) => ({ key: space.id, value: space.id, label: label(space) }));
  return (
    <SelfTestView
      groups={groups}
      setup={(busy) => (
        <>
          {scopeError && <ServiceNotice color="error" title={t("rework.selftest.page.scopeError")} />}
          <Select
            size="medium"
            disabled={busy || !spaces.length}
            label={t("rework.selftest.path.root")}
            options={[{ key: "none", value: "", label: t("rework.selftest.path.sharedOnly") }, ...options(roots)]}
            value={path[0]?.id ?? ""}
            onChange={onSelect}
          />
          {path.map((parent, index) => {
            if (parent.kind !== "organization" && parent.kind !== "team") return null;
            const children = spaces.filter((space) => linked(parent, space));
            return (
              <Select
                key={parent.id}
                size="medium"
                disabled={busy || !children.length}
                label={t(`rework.selftest.path.${parent.kind === "organization" ? "chooseTeam" : "chooseProject"}`)}
                options={[
                  { key: "stop", value: parent.id, label: t("rework.selftest.path.stop", { name: label(parent) }) },
                  ...options(children),
                ]}
                value={path[index + 1]?.id ?? parent.id}
                onChange={onSelect}
              />
            );
          })}
        </>
      )}
      manual={(props) => (
        <WeaverManualTests
          {...props}
          context={context}
          campaignContext={campaignTeam ? { ...levelContext("team"), roles: campaignTeam.roles } : undefined}
          campaignScopeName={campaignTeam?.name}
          expiryScopeName={selected?.name}
        />
      )}
    />
  );
}
