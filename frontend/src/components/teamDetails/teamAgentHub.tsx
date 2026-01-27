import { AnyAgent } from "../../common/agent";

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
  return <></>;
}
