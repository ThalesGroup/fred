import { KeyCloakService } from "../../../security/KeycloakService";
import { personalTeamId } from "../../components/shared/utils/teamId";

// Control Plane resolves the URL alias; runtime authorization needs the full ID.
export function canonicalizeRuntimeTeamId(teamId: string): string {
  return teamId === "personal" ? personalTeamId(KeyCloakService.GetUserId() ?? "") : teamId;
}
