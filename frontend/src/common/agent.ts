// agents.ts (Updated to use Functional Color Hints)

import { SvgIconTypeMap } from "@mui/material";
import { OverridableComponent } from "@mui/material/OverridableComponent";
import { Agent } from "../slices/agentic/agenticOpenApi";

// Import necessary Material UI Icons
import AssignmentTurnedInIcon from "@mui/icons-material/AssignmentTurnedIn"; // Report/Execution (Success)
import AutoStoriesIcon from "@mui/icons-material/AutoStories"; // General (Secondary/Default)
import DataObjectIcon from "@mui/icons-material/DataObject"; // Data (Info)
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile"; // Default for drafting (Warning)

// --- Type Definitions ---

export type AnyAgent = Agent;

export const isLikelyV2DefinitionAgent = (agent: AnyAgent): boolean => {
  const classPath = agent.class_path?.trim();
  if (!classPath) {
    return false;
  }

  return classPath.endsWith("Definition") || classPath.includes(".v2.");
};

// Define the type for the MUI Icon component property
type MuiIcon = OverridableComponent<SvgIconTypeMap<{}, "svg">>;

// MODIFIED: Define custom functional color hints
export type AgentColorHint = "data" | "document" | "execution" | "general";

interface AgentVisuals {
  Icon: MuiIcon;
  /** Functional color hint: data, document, execution, or general. */
  colorHint: AgentColorHint; // Use the new type here
}

// --- Keyword to Icon Mapping Logic ---

/**
 * Determines the best icon and color hint for an agent based on its functional role.
 * @param agent The agent object.
 * @returns An object containing the icon component and a functional color hint.
 */
export const getAgentVisuals = (agent: AnyAgent): AgentVisuals => {
  const roleText = agent.tuning.role.toLowerCase();

  // 1. Data/Knowledge/Information
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

  // 2. Execution/Report/Analysis/Tool (Grouped for 'execution')
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

  // 3. Drafting/Content Creation
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

  // 4. Fallback for unclassified agents
  return {
    Icon: AutoStoriesIcon,
    colorHint: "general", // Custom hint
  };
};
