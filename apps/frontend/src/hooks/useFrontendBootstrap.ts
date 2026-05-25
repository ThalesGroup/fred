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
  permissionItems: string[];
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
 * - use `availableTeams` for team navigation and `permissionItems` for route/UI
 *   gates when a boolean summary is not enough
 *
 * Example:
 * - `const { activeTeam, availableTeams, isLoading } = useFrontendBootstrap();`
 */
export function useFrontendBootstrap(): FrontendBootstrapState {
  const { data, isLoading, isFetching, refetch } = useGetFrontendBootstrapControlPlaneV1FrontendBootstrapGetQuery(
    undefined,
    {
      refetchOnMountOrArgChange: true,
    },
  );

  return {
    bootstrap: data,
    activeTeam: data?.active_team,
    availableTeams: data?.available_teams ?? [],
    permissionItems: data?.permissions?.items ?? [],
    isLoading: isLoading || (isFetching && !data),
    refetch,
  };
}
