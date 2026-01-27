import { useTranslation } from "react-i18next";
import { AnyAgent } from "../../common/agent";
import { usePermissions } from "../../security/usePermissions";
import { AgentGridManager } from "../agentHub/AgentGridManager";

// mock agents (todo: get them from back)
const agents: AnyAgent[] = [
  {
    type: "leader",
    name: "TeamLeader",
    enabled: true,
    tuning: {
      role: "Team Leader",
      description: "Coordinates team activities and delegates tasks to specialists",
      tags: ["coordination", "leadership"],
    },
    chat_options: {
      search_policy_selection: true,
      libraries_selection: true,
      attach_files: true,
    },
    crew: ["DataAnalyst", "DocumentWriter", "CodeReviewer"],
  },
  {
    type: "agent",
    name: "DataAnalyst",
    enabled: true,
    tuning: {
      role: "Data Analysis Expert",
      description: "Specializes in analyzing datasets and providing insights",
      tags: ["data", "analytics", "visualization"],
    },
    chat_options: {
      attach_files: true,
      libraries_selection: true,
    },
  },
  {
    type: "agent",
    name: "DocumentWriter",
    enabled: true,
    tuning: {
      role: "Technical Documentation Specialist",
      description: "Creates and maintains high-quality technical documentation",
      tags: ["documentation", "writing", "content"],
    },
    chat_options: {
      attach_files: true,
      libraries_selection: true,
      documents_selection: true,
    },
  },
  {
    type: "agent",
    name: "CodeReviewer",
    enabled: true,
    tuning: {
      role: "Code Review and Quality Analysis",
      description: "Performs thorough code reviews and suggests improvements",
      tags: ["code", "review", "quality"],
    },
    chat_options: {
      attach_files: true,
    },
  },
  {
    type: "agent",
    name: "SecurityAuditor",
    enabled: false,
    tuning: {
      role: "Security and Compliance Auditor",
      description: "Identifies security vulnerabilities and ensures compliance",
      tags: ["security", "audit", "compliance"],
    },
    chat_options: {
      attach_files: true,
      libraries_selection: true,
    },
  },
];

export function TeamAgentHub() {
  const { t } = useTranslation();

  // Permissions
  // todo: base perm on ReBAC
  const { can } = usePermissions();
  const canEditAgents = can("agents", "update");
  const canCreateAgents = can("agents", "create");

  const handleRefetch = () => {
    // TODO: Implement when backend is ready
    console.log("Refresh team agents");
  };

  return (
    <AgentGridManager
      agents={agents}
      isLoading={false}
      canEdit={canEditAgents}
      canCreate={canCreateAgents}
      canDelete={canEditAgents}
      onRefetchAgents={handleRefetch}
      showRestoreButton={false}
      showA2ACard={true}
      emptyStateMessage={t("teamDetails.noAgents")}
    />
  );
}
