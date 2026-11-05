// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// Weaver has no admitted turn-free vision service. Keep structural analysis and
// the existing rules-only explanation; never query the retired profile catalog.
export interface VisionProfile {
  profile_id: string;
  name?: string;
  display_name?: string | null;
  model_name?: string | null;
  supports_vision?: boolean;
}
export interface VisionAvailability {
  available: boolean | null;
  visionProfiles: VisionProfile[];
}
export function usePlatformVisionProfiles(_skip: boolean): VisionProfile[] {
  return [];
}
export function useVisionAvailability(_spaceId?: string, _agentInstanceId?: string): VisionAvailability {
  return { available: false, visionProfiles: [] };
}
