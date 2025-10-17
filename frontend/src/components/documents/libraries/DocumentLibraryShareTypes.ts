import { UserTagRelation } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export type DocumentLibraryShareAudience = "user" | "group";

export interface DocumentLibraryShareSelectableTarget {
  id: string;
  displayName: string;
  audience: DocumentLibraryShareAudience;
}

export interface DocumentLibraryPendingRecipient extends DocumentLibraryShareSelectableTarget {
  relation: UserTagRelation;
}
