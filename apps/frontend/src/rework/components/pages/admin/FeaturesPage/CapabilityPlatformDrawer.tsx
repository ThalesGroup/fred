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

// The drawer of a capability's platform-wide settings: it mounts the panel the
// capability's UI plugin declares, routes its calls to the capability pod, and
// tells it whether the viewer may write (platform admin or feature manager).

import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useDispatch } from "react-redux";
import { setCapabilityBaseUrls } from "../../../../../common/capabilityRoutingSlice";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useUserCapabilities } from "../../../../core/hooks/useUserCapabilities";
import { platformPanelFor } from "../../../../features/capabilities/platformPanelRegistry";
import { capabilityLabel } from "./capabilityEnablement";

interface Props {
  capability: CapabilityEnablementItem | null;
  allCapabilities: readonly CapabilityEnablementItem[];
  onClose: () => void;
}

export function CapabilityPlatformDrawer({ capability, allCapabilities, onClose }: Props) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const { canManageFeatures } = useUserCapabilities();
  const Panel = capability ? platformPanelFor(capability.id) : undefined;

  useEffect(() => {
    if (capability?.route_base_url) {
      dispatch(setCapabilityBaseUrls({ [capability.id]: capability.route_base_url }));
    }
  }, [capability?.id, capability?.route_base_url, dispatch]);

  return (
    <InlineDrawer
      open={Boolean(capability && Panel)}
      onClose={onClose}
      title={
        capability ? t("rework.admin.capabilities.platformDrawer.title", { name: capabilityLabel(t, capability) }) : ""
      }
      width="480px"
    >
      {capability && Panel && (
        <Panel capability={capability} allCapabilities={allCapabilities} canManage={canManageFeatures} />
      )}
    </InlineDrawer>
  );
}
