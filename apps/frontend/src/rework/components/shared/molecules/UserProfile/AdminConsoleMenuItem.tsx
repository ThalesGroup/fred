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
import { useLocation, useNavigate } from "react-router-dom";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { useOrganizationSupervisionAccess } from "@core/hooks/useOrganizationSupervisionAccess";
import { useOrganizationOwner } from "@core/hooks/useOrganizationOwner";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { canEnterAdminSection } from "@core/guards/Protected";
import { skipsBusinessBootstrap } from "@core/utils/adminRoutes";

/** Any admin-tier role opens the console, so a delegated role holder can reach the one page they own. */
export function AdminConsoleMenuItem({ onClose }: { onClose: () => void }) {
  const { pathname } = useLocation();
  // Platform pages never mount the business bootstrap; the platform role alone shows Admin there.
  const capabilities = useUserCapabilities(skipsBusinessBootstrap(pathname));
  const organization = useOrganizationOwner();
  const supervision = useOrganizationSupervisionAccess();
  const manager = useManagerPlatformAdmin();
  const offered =
    supervision.offered ||
    manager.isAdmin ||
    canEnterAdminSection({ ...capabilities, canManageFeatures: organization.isOwner });
  return offered ? <AdminConsoleLink to="/admin" onClose={onClose} /> : null;
}

/** A platform admin without an organization: the console is all there is. */
export function AdminConsoleLink({ to, onClose }: { to: string; onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <MenuPopoverItem
      icon={{ category: "outlined", type: "admin_panel_settings" }}
      label={t("rework.mainNav.adminConsole")}
      onClick={() => {
        onClose();
        navigate(to);
      }}
    />
  );
}
