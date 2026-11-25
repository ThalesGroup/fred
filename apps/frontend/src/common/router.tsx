import TeamKnowledgeBasesPage from "../rework/components/pages/TeamKnowledgeBasesPage/TeamKnowledgeBasesPage";
import KnowledgeBaseDocumentsPage from "../rework/components/pages/TeamKnowledgeBasesPage/KnowledgeBaseDocumentsPage";
import { WorkingOrganizationProvider } from "@core/hooks/useWorkingOrganization";
import WeaverFeaturePage from "@rework/features/weaver/WeaverFeaturePage";
import { isWeaverContentRoute } from "@core/utils/weaverContentRoute";
import PlatformAccessPage from "@components/pages/admin/PlatformAccessPage/PlatformAccessPage";
import PlatformAccessDeniedPage from "@components/pages/PlatformAccessPage/PlatformAccessDeniedPage";
import FreeEnrollmentPage from "@components/pages/PlatformAccessPage/FreeEnrollmentPage";
// Copyright Thales 2025
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

import AdminTeamsPage from "@components/pages/admin/AdminTeamsPage/AdminTeamsPage.tsx";
import AnalyticsPage from "@components/pages/admin/AnalyticsPage/AnalyticsPage.tsx";
import AnnouncementsPage from "@components/pages/admin/AnnouncementsPage/AnnouncementsPage.tsx";
import ConversationTraceInspectorPage from "@components/pages/admin/ConversationTraces/ConversationTraceInspectorPage";
import { ConversationTraceSettingsPage } from "@components/pages/admin/ConversationTraces/ConversationTraceSettings";
import ConversationTraceListPage from "@components/pages/admin/ConversationTraces/ConversationTraceListPage";
import FeaturesPage from "@components/pages/admin/FeaturesPage/FeaturesPage.tsx";
import PlatformPromptPage from "@components/pages/admin/PlatformPromptPage/PlatformPromptPage.tsx";
import HomeSettingsSection from "@components/pages/admin/UiSettingsPage/HomeSettingsSection";
import UiSettingsPage from "@components/pages/admin/UiSettingsPage/UiSettingsPage.tsx";
import PlatformRolesPage from "@components/pages/admin/PlatformRolesPage/PlatformRolesPage.tsx";
import DocumentViewerPage from "@components/pages/DocumentViewerPage/DocumentViewerPage.tsx";
import { GcuPageContent } from "@components/pages/GcuPage/GcuPage.tsx";
import GdprPage from "@components/pages/GdprPage/GdprPage.tsx";
import HomePage from "@components/pages/HomePage/HomePage.tsx";
import ManagedChatPage from "@components/pages/ManagedChatPage/ManagedChatPage.tsx";
import MarketplaceTeams from "@components/pages/marketplace/MarketplaceTeams/MarketplaceTeams.tsx";
import MarketplacePage from "@components/pages/marketplace/MarketplacePage";
import PptFillerHelpPage from "@components/pages/PptFillerHelpPage/PptFillerHelpPage.tsx";
import SkillsPage from "@components/pages/SkillsPage/SkillsPage";
import PromptsPage from "@components/pages/PromptsPage/PromptsPage.tsx";
import TeamProjectsPage from "@components/pages/TeamProjectsPage/TeamProjectsPage.tsx";
import TeamResourcesPage from "@components/pages/TeamResourcesPage/TeamResourcesPage.tsx";
import TeamWikiPage from "@components/pages/TeamWikiPage/TeamWikiPage.tsx";
import TeamLandingPage from "@components/pages/TeamSettingsPage/TeamLandingPage";
import TeamSettingsPage, { OrganizationObserversPage } from "@components/pages/TeamSettingsPage/TeamSettingsPage.tsx";
import TeamUsagePage from "@components/pages/TeamUsagePage/TeamUsagePage.tsx";
import ReleaseNotesPage from "@components/pages/ReleaseNotesPage/ReleaseNotesPage.tsx";
import TeamAgentsPage from "@components/pages/TeamAgentsPage/TeamAgentsPage.tsx";
import TeamApplicationHostPage from "@components/pages/TeamApplicationHostPage/TeamApplicationHostPage.tsx";
import TeamApplicationsPage from "@components/pages/TeamApplicationsPage/TeamApplicationsPage.tsx";
import UserSettingsPage from "@components/pages/UserSettingsPage/UserSettingsPage.tsx";
import MainLayout from "@shared/layouts/MainLayout/MainLayout.tsx";
import React, { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { createBrowserRouter, Navigate, RouteObject, useParams, Outlet, useLocation } from "react-router-dom";
import LoadingWithProgress from "../components/LoadingWithProgress";
import { Protected } from "@core/guards/Protected";
import { adminIndexPath } from "@core/guards/organizationOwnerPages";
import { useConversationTraceAccess } from "@core/hooks/useConversationTraceAccess";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { PageError } from "@components/pages/PageError/PageError.tsx";
import Unauthorized from "@components/pages/PageUnauthorized/PageUnauthorized.tsx";
import { getConfig } from "./config";

import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import MonitorPage from "@components/pages/admin/MonitorPage/MonitorPage";
import OrganizationsPage from "@components/pages/admin/OrganizationsPage/OrganizationsPage";
import { useOrganizationOwner } from "@core/hooks/useOrganizationOwner";
import ManagerArea from "@core/guards/ManagerArea";
import OnboardingGuard from "@core/guards/OnboardingGuard";
import ProvisioningPage from "@components/pages/admin/ProvisioningPage/ProvisioningPage";
import AnnouncementStack from "../rework/features/announcements/AnnouncementStack";
import PatchNoteGate from "../rework/features/announcements/PatchNoteGate";
import appStyles from "../app/App.module.css";

import OrganizationSupervisionPage from "@components/pages/OrganizationSupervisionPage/OrganizationSupervisionPage";
import {
  OrganizationSupervisionAccessProvider,
  useOrganizationSupervisionAccess,
} from "@core/hooks/useOrganizationSupervisionAccess";

const basename = getConfig().frontend_basename;

function AdmittedContent() {
  const { pathname } = useLocation();
  const agentManagement = isWeaverContentRoute(pathname);
  return (
    <OnboardingGuard>
      <WorkingOrganizationProvider>
        <OrganizationSupervisionAccessProvider>
          <ManagerArea>
            {(business) => (
              <div className={appStyles.appContent}>
                {business && !agentManagement && <AnnouncementStack />}
                <div className={appStyles.routedContent}>
                  {business && !agentManagement && <PatchNoteGate />}
                  <Outlet />
                </div>
              </div>
            )}
          </ManagerArea>
        </OrganizationSupervisionAccessProvider>
      </WorkingOrganizationProvider>
    </OnboardingGuard>
  );
}

// Remounts cleanly on every agent change — prevents stale hook state leaking across agents.
const ManagedChatPageRoute = () => {
  const { agentInstanceId } = useParams<{ agentInstanceId: string }>();
  return <ManagedChatPage key={agentInstanceId} />;
};

const OrganizationFeaturesRoute = () => {
  const { organizationId } = useOrganizationOwner();
  return organizationId ? <FeaturesPage key={organizationId} organizationId={organizationId} /> : null;
};

const OrganizationPromptRoute = () => {
  const { organizationId } = useOrganizationOwner();
  return organizationId ? <PlatformPromptPage key={organizationId} organizationId={organizationId} /> : null;
};

const AdminIndexRoute = () => {
  const supervision = useOrganizationSupervisionAccess();
  const traces = useConversationTraceAccess();
  const { isLoading, ...capabilities } = useUserCapabilities(traces.isLoading || traces.canRead || traces.canManage);
  const manager = useManagerPlatformAdmin();
  const organization = useOrganizationOwner();
  if (organization.isLoading || (organization.isFetching && !organization.currentData)) return null;
  if (isLoading || manager.isLoading || supervision.loading) return null;
  const target = adminIndexPath({
    capabilities: { ...capabilities, canManageFeatures: organization.isOwner },
    supervision: supervision.allowed,
    platformAccessEnabled: !!getConfig()?.platform_access_enabled,
    platformOwner: manager.isAdmin,
  });
  return <Navigate to={target} replace />;
};

const WeaverSelfTests = lazy(() => import("@components/pages/admin/SelfTestPage/WeaverSelfTestPage"));
const TaskPlayground = lazy(() => import("../pages/TaskPlayground"));
const LibraryTreePlayground = lazy(() => import("@components/pages/LibraryTreePlayground/LibraryTreePlayground.tsx"));
// Lazy: the Help Center chunk carries its whole markdown corpus (HELP-01).
const HelpCenterPage = lazy(() => import("@components/pages/HelpCenterPage/HelpCenterPage.tsx"));

// Bare `/help` picks the content language from the app language, then the
// page itself redirects to the first section.
const HelpIndexRoute = () => {
  const { i18n } = useTranslation();
  const lang = i18n.language?.toLowerCase().startsWith("en") ? "en" : "fr";
  return <Navigate to={`/help/${lang}`} replace />;
};

const SuspenseWrapper = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<LoadingWithProgress />}>{children}</Suspense>
);

const applicationRoutes: RouteObject[] = [
  { path: "/platform-access-denied", element: <PlatformAccessDeniedPage /> },
  { path: "/join/:token", element: <FreeEnrollmentPage /> },
  {
    path: "/",
    element: <MainLayout />,
    children: [
      {
        // Bare `/` lands on the Home dashboard (#2298). The team switcher lives
        // in the organization nav panel; the personal-space agents page is reached from
        // there rather than being the app's landing route.
        index: true,
        element: <Navigate to="/home" replace />,
      },
      {
        // The organization's landing: its panel (Sidebar ORGANIZATION mode) holds the
        // team list; this is the content-area page.
        path: "home",
        element: <HomePage />,
      },
      {
        path: "team/:teamId/agents",
        element: <TeamAgentsPage />,
      },
      {
        path: "team/:teamId/managed-chat/:agentInstanceId",
        element: <ManagedChatPageRoute />,
      },
      {
        path: "team/:teamId/projects",
        element: <TeamProjectsPage />,
      },
      {
        path: "team/:teamId/skills",
        element: <SkillsPage />,
      },
      {
        path: "team/:teamId/prompts",
        element: <PromptsPage />,
      },
      {
        path: "team/:teamId/resources",
        element: <TeamResourcesPage />,
      },
      {
        path: "team/:teamId/knowledge-bases",
        element: <TeamKnowledgeBasesPage />,
      },
      {
        path: "team/:teamId/knowledge-bases/:instanceId",
        element: <KnowledgeBaseDocumentsPage />,
      },
      {
        path: "team/:teamId/wiki",
        element: <TeamWikiPage />,
      },
      {
        // Same page: the slug selects which article is open, so a wiki page is
        // deep-linkable and the browser's back button walks the pages.
        path: "team/:teamId/wiki/:slug",
        element: <TeamWikiPage />,
      },
      {
        path: "team/:teamId/apps",
        element: <TeamApplicationsPage />,
      },
      {
        // Resolve the authorized application before mounting its hosted UI.
        path: "team/:teamId/apps/:appId/*",
        element: <TeamApplicationHostPage />,
      },
      {
        path: "team/:teamId/usage",
        element: <TeamUsagePage />,
      },
      {
        // Team settings render in the main content area while the sidebar shell
        // (coloured team banner + dimmed team rail) stays mounted. Bare
        // `/settings` lands on the members section.
        path: "team/:teamId/settings",
        element: <Navigate to="members" replace />,
      },
      {
        path: "team/:teamId/settings/:section",
        element: <TeamSettingsPage />,
      },
      {
        // Resolve content and governance independently through Weaver authorization.
        path: "team/:teamId",
        element: <TeamLandingPage />,
      },
      // The marketplace opens on its first menu entry.
      { path: "marketplace", element: <Navigate to="/marketplace/teams" replace /> },
      {
        path: "marketplace/teams",
        element: <MarketplaceTeams />,
      },
      {
        path: "marketplace/prompts",
        element: <MarketplacePage kind="prompt" />,
      },
      {
        path: "marketplace/agents",
        element: <MarketplacePage kind="agent" />,
      },
      { path: "marketplace/skills", element: <MarketplacePage kind="skill" /> },
      {
        path: "admin",
        element: <AdminIndexRoute />,
      },
      {
        path: "admin/supervision",
        element: <OrganizationSupervisionPage />,
      },
      {
        path: "admin/organizations",
        element: <OrganizationsPage />,
      },
      {
        path: "admin/monitor",
        element: <MonitorPage />,
      },
      {
        path: "admin/provisioning",
        element: <ProvisioningPage />,
      },
      {
        // Common instructions belong to the active organization and its direct Owner.
        path: "admin/platform-prompt",
        element: (
          <Protected requires="features">
            <OrganizationPromptRoute />
          </Protected>
        ),
      },
      {
        path: "admin/teams",
        element: (
          <Protected requires="teamRoster">
            <AdminTeamsPage />
          </Protected>
        ),
      },
      {
        // Platform roles (PLATFORM-ADMIN-DELEGATION-RFC.md §3.7, #2405). Gated
        // on the admin role like the backend's `can_administer_users`; the
        // stricter bootstrap-root-only rules on the platform_admin relation
        // are enforced server-side and only mirrored in the page's UI.
        path: "admin/platform-access",
        element: (
          <Protected requires="platformAccess">
            <PlatformAccessPage />
          </Protected>
        ),
      },
      {
        path: "admin/platform-roles",
        element: (
          <Protected requires="admin">
            <PlatformRolesPage />
          </Protected>
        ),
      },
      {
        path: "admin/tasks",
        element: (
          <Protected requires="admin">
            <WeaverFeaturePage feature="tasks" />
          </Protected>
        ),
      },
      {
        path: "admin/conversation-traces/settings",
        element: (
          <Protected requires="conversationTraceSettings">
            <ConversationTraceSettingsPage />
          </Protected>
        ),
      },
      {
        path: "admin/observers",
        element: (
          <Protected requires="conversationTraceSettings">
            <OrganizationObserversPage />
          </Protected>
        ),
      },
      {
        path: "admin/conversation-traces",
        element: (
          <Protected requires="conversationTraces">
            <ConversationTraceListPage />
          </Protected>
        ),
      },
      {
        path: "admin/conversation-traces/:sessionId",
        handle: { hideSectionNavigation: true },
        element: (
          <Protected requires="conversationTraces">
            <ConversationTraceInspectorPage />
          </Protected>
        ),
      },
      {
        path: "admin/analytics",
        element: (
          <Protected requires="observer">
            <AnalyticsPage />
          </Protected>
        ),
      },
      {
        // Existing Features surface, guarded by the user's organization admin role.
        // Agent discovery is read-only; the Rust API checks organization can_manage.
        path: "admin/features",
        element: (
          <Protected requires="features">
            <OrganizationFeaturesRoute />
          </Protected>
        ),
      },
      {
        // Platform announcements: the banners every authenticated user sees at
        // the top of the app. Full platform-admin gate, matching the backend's
        // `can_manage_platform` on the admin routes.
        path: "admin/annonces",
        element: (
          <Protected requires="admin">
            <AnnouncementsPage />
          </Protected>
        ),
      },
      {
        // Platform UI theme settings; same platform-admin gate as the backend's
        // `can_manage_platform` on /admin/platform/ui-settings.
        path: "admin/interface",
        element: (
          <Protected requires="admin">
            <UiSettingsPage />
          </Protected>
        ),
      },
      {
        path: "admin/home-settings",
        element: (
          <Protected requires="features">
            <HomeSettingsSection />
          </Protected>
        ),
      },
      {
        path: "admin/marketplaces",
        element: <Navigate to="/marketplace/prompts" replace />,
      },
      {
        path: "admin/self-test",
        element: (
          <SuspenseWrapper>
            <WeaverSelfTests />
          </SuspenseWrapper>
        ),
      },
      {
        // Corpus audit (#2112): platform-admin-only surface over the document
        // store audit/fix endpoints (`CAN_MANAGE_PLATFORM`) — same gate as the
        // other admin-only pages above.
        path: "admin/corpus-audit",
        element: (
          <Protected requires="admin">
            <WeaverFeaturePage feature="audit" />
          </Protected>
        ),
      },
      {
        path: "admin/migration",
        element: (
          <Protected requires="admin">
            <WeaverFeaturePage feature="migration" />
          </Protected>
        ),
      },
      {
        path: "dev/tasks",
        element: import.meta.env.DEV ? (
          <SuspenseWrapper>
            <TaskPlayground />
          </SuspenseWrapper>
        ) : (
          <PageError />
        ),
      },
      {
        path: "dev/library",
        element: import.meta.env.DEV ? (
          <SuspenseWrapper>
            <LibraryTreePlayground />
          </SuspenseWrapper>
        ) : (
          <PageError />
        ),
      },
      {
        path: "*",
        element: <PageError />,
      },
    ].filter(Boolean),
  },
  {
    path: "/bootstrap",
    element: <Navigate to="/" replace />,
  },
  {
    path: "/documents/:uid",
    element: <DocumentViewerPage />,
  },
  {
    path: "/gcu",
    element: <GcuPageContent accepted />,
  },
  {
    path: "/gdpr",
    element: <GdprPage />,
  },
  {
    path: "/release-notes",
    element: <ReleaseNotesPage />,
  },
  {
    // Help Center (HELP-01) — own tab, no app chrome, shareable URLs.
    path: "/help",
    element: <HelpIndexRoute />,
  },
  {
    path: "/help/:lang/:sectionId?/:pageId?",
    element: (
      <SuspenseWrapper>
        <HelpCenterPage />
      </SuspenseWrapper>
    ),
  },
  {
    // PPT Filler capability documentation — opened in a new tab from the
    // agent-creation form, so it renders without the app chrome.
    path: "/ppt-filler-help",
    element: <PptFillerHelpPage />,
  },
  {
    path: "/settings",
    element: <UserSettingsPage />,
  },
  {
    path: "unauthorized",
    element: <Unauthorized />,
  },
];

export const routes: RouteObject[] = [{ element: <AdmittedContent />, children: applicationRoutes }];

export const router = createBrowserRouter(routes, { basename });
