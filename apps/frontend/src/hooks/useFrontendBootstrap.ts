import {
  useGetFrontendBootstrapControlPlaneV1FrontendBootstrapGetQuery,
  type FrontendBootstrap,
  type Team,
  type TeamWithPermissions,
} from "../slices/controlPlane/controlPlaneOpenApi";

export type FrontendBootstrapState = {
  bootstrap?: FrontendBootstrap;
  activeTeam?: TeamWithPermissions;
  availableTeams: Team[];
  isLoading: boolean;
  refetch: () => void;
};

/**
 * Read the control-plane-owned frontend bootstrap in one place.
 *
 * Why this hook exists:
 * - the migrated shell should derive current user, active team, available teams,
 *   and permission summary from one control-plane bootstrap payload instead of
 *   mixing multiple legacy endpoints
 *
 * How to use it:
 * - call the hook in shell or page components that need bootstrap-owned state
 * - use `activeTeam` for the current personal/team context during the Phase 5
 *   convergence work
 * - use `availableTeams` for team navigation; use `useUserCapabilities()` for
 *   org-level gates and `useTeamCapabilities(team)` for team-level gates
 *   instead of reading `bootstrap.permissions` directly (see
 *   `docs/swift/platform/FRONTEND-AUTHZ-PATTERN.md`)
 *
 * Example:
 * - `const { activeTeam, availableTeams, isLoading } = useFrontendBootstrap();`
 */
export function useFrontendBootstrap(): FrontendBootstrapState {
  // #2148: no longer forces a refetch on every mount — the control-plane
  // enrichment behind this endpoint does one OpenFGA `Read` plus one
  // Keycloak lookup per team, and this hook mounts on nearly every page.
  // RTK Query's own cache (backed by `providesTags`/`invalidatesTags` on
  // this endpoint and every team mutation, see controlPlaneApiEnhancements.ts)
  // keeps this fresh for changes made in this session.
  //
  // PR #2160 review (Codex, P1): `TeamSelectionNavbar` keeps this query
  // permanently subscribed across every route (see `MainLayout.tsx`), so
  // RTK Query's unused-data eviction never runs, and tags alone only react
  // to mutations dispatched from this browser's own Redux store — a team
  // membership or platform role change made from another session/browser
  // would otherwise stay invisible here for the rest of the login session.
  // `refetchOnMountOrArgChange: 60` bounds that: any page navigation that
  // remounts a bootstrap consumer (most pages do) revalidates if the cached
  // data is older than 60s. Shorter than the KPI presets' 300s TTL because
  // this drives admin-gating UI (`useUserCapabilities`), not analytics
  // display — real backend authorization checks are unaffected either way.
  const { data, isLoading, isFetching, refetch } = useGetFrontendBootstrapControlPlaneV1FrontendBootstrapGetQuery(
    undefined,
    { refetchOnMountOrArgChange: 60 },
  );

  return {
    bootstrap: data,
    activeTeam: data?.active_team,
    availableTeams: data?.available_teams ?? [],
    isLoading: isLoading || (isFetching && !data),
    refetch,
  };
}
