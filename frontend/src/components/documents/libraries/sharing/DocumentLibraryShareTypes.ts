import { TagShareRequest } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface DocumentLibraryPendingRecipient extends TagShareRequest {
  displayName: string;
}
