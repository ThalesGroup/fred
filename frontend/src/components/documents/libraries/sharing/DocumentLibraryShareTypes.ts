import { TagShareRequest, UserSummary } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export type DocumentLibraryPendingRecipient = UserPendingRecipient;

export interface UserPendingRecipient extends TagShareRequest {
  target_type: "user";
  data: UserSummary;
}
