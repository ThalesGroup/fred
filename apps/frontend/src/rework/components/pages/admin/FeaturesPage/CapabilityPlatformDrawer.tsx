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

// Organization owners manage the common template for a logical pod.

import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { setCapabilityBaseUrls } from "../../../../../common/capabilityRoutingSlice";
import { useTranslation } from "react-i18next";
import { useSpaceAccess } from "../../../../core/hooks/useSpaceAccess";
import { platformPanelFor } from "../../../../features/capabilities/platformPanelRegistry";

interface Props {
  capability: { id: string; name: string; route_base_url?: string | null } | null;
  organizationId: string;
  runtimeId?: string;
  onClose: () => void;
}

export function CapabilityPlatformDrawer({ capability, organizationId, runtimeId, onClose }: Props) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const access = useSpaceAccess(organizationId, "manage");
  const Panel = capability ? platformPanelFor(capability.id) : undefined;

  useEffect(() => {
    if (capability?.route_base_url && runtimeId)
      dispatch(
        setCapabilityBaseUrls({
          [`${organizationId}/${runtimeId}/${capability.id}`]: capability.route_base_url,
        }),
      );
  }, [capability?.id, capability?.route_base_url, organizationId, runtimeId, dispatch]);

  return (
    <InlineDrawer
      open={Boolean(capability && Panel)}
      onClose={onClose}
      title={
        capability
          ? t("rework.admin.capabilities.platformDrawer.title", {
              name: t(capability.name, { defaultValue: capability.name }),
            })
          : ""
      }
      width="480px"
    >
      {capability && Panel && (
        <Panel
          key={`${organizationId}/${runtimeId}/${capability.id}`}
          capability={capability}
          organizationId={organizationId}
          runtimeId={runtimeId ?? ""}
          baseUrl={capability.route_base_url ?? null}
          canManage={access.allowed}
        />
      )}
    </InlineDrawer>
  );
}
