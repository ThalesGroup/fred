import { useGetVisionAvailabilityQuery } from "../../../../slices/knowledgeFlow/knowledgeFlowVisionApi";

export interface VisionAvailability {
  available: boolean | null;
}

export function visionAvailability(available: boolean | undefined, failed = false): VisionAvailability {
  return { available: available ?? (failed ? false : null) };
}

export function useVisionAvailability(skip = false): VisionAvailability {
  const query = useGetVisionAvailabilityQuery(undefined, { skip });
  return visionAvailability(query.data?.available, query.isError);
}
