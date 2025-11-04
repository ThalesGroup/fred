import { GroupSummary, TagShareRequest, UserSummary } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export type DocumentLibraryPendingRecipient = UserPendingRecipient | GroupPendingRecipient;

export interface UserPendingRecipient extends TagShareRequest {
  target_type: "user";
  data: UserSummary;
}

export interface GroupPendingRecipient extends TagShareRequest {
  target_type: "group";
  data: GroupSummary;
}
