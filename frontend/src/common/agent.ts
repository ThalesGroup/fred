// agents.ts (Updated to use Functional Color Hints)

import { SvgIconTypeMap } from "@mui/material";
import { OverridableComponent } from "@mui/material/OverridableComponent";
import { Agent, Leader } from "../slices/agentic/agenticOpenApi";

// Import necessary Material UI Icons
import AssignmentTurnedInIcon from "@mui/icons-material/AssignmentTurnedIn"; // Report/Execution (Success)
import AutoStoriesIcon from "@mui/icons-material/AutoStories"; // General (Secondary/Default)
import DataObjectIcon from "@mui/icons-material/DataObject"; // Data (Info)
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile"; // Default for drafting (Warning)
import StarIcon from "@mui/icons-material/Star"; // Leader/Star (Primary)

// --- Type Definitions ---

export type AnyAgent = ({ type: "agent" } & Agent) | ({ type: "leader" } & Leader);

export const isLeader = (a: AnyAgent): a is { type: "leader" } & Leader => a.type === "leader";

// Define the type for the MUI Icon component property
type MuiIcon = OverridableComponent<SvgIconTypeMap<{}, "svg">>;

// MODIFIED: Define custom functional color hints
export type AgentColorHint = "leader" | "data" | "document" | "execution" | "general";

interface AgentVisuals {
  Icon: MuiIcon;
  /** Functional color hint: leader, data, document, execution, or general. */
  colorHint: AgentColorHint; // Use the new type here
}

// --- Keyword to Icon Mapping Logic ---

/**
 * Determines the best icon and color hint for an agent based on its functional role.
 * @param agent The agent object (Leader or Agent).
 * @returns An object containing the icon component and a functional color hint.
 */
export const getAgentVisuals = (agent: AnyAgent): AgentVisuals => {
  const roleText = agent.role.toLowerCase();

  // 1. Priority: Supervisor/Leader
  if (isLeader(agent)) {
    return {
      Icon: StarIcon,
      colorHint: "leader", // Custom hint
    };
  }

  // 2. Data/Knowledge/Information
  if (
    roleText.includes("data") ||
    roleText.includes("information") ||
    roleText.includes("knowledge") ||
    roleText.includes("retrieve")
  ) {
    return {
      Icon: DataObjectIcon,
      colorHint: "data", // Custom hint
    };
  }

  // 3. Execution/Report/Analysis/Tool (Grouped for 'execution')
  if (
    roleText.includes("report") ||
    roleText.includes("summary") ||
    roleText.includes("analysis") ||
    roleText.includes("execute") ||
    roleText.includes("tool")
  ) {
    return {
      Icon: AssignmentTurnedInIcon,
      colorHint: "execution", // Custom hint
    };
  }

  // 4. Drafting/Content Creation
  if (
    roleText.includes("document") ||
    roleText.includes("file") ||
    roleText.includes("slide") ||
    roleText.includes("draft") ||
    roleText.includes("writer")
  ) {
    return {
      Icon: InsertDriveFileIcon,
      colorHint: "document", // Custom hint
    };
  }

  // 5. Fallback for unclassified agents
  return {
    Icon: AutoStoriesIcon,
    colorHint: "general", // Custom hint
  };
};
