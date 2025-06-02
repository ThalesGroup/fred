// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { Period } from "../utils/period.tsx";
import { ClusterConsumption, ClusterFootprint } from "../frugalit/slices/api.tsx";
/**
 * Interface representing the structure of the Footprint Context.
 *
 * @interface FootprintContextStruct
 *
 * @property {string} period - The current period for which the footprints are being tracked.
 * @property {ClusterFootprint} currentClusterFootprints - The current cluster footprints data.
 * @property {ClusterFootprint[]} selectedClusterFootprints - The selected cluster footprints data.
 * @property {ClusterFootprint[]} allClusterFootprints - All available cluster footprints data.
 * @property {ClusterConsumption | undefined} currentCarbonConsumption - The current carbon consumption data.
 * @property {ClusterConsumption | undefined} currentEnergyConsumption - The current energy consumption data.
 * @property {ClusterConsumption | undefined} currentCostConsumption - The current cost consumption data.
 * @property {(fullname: string) => void} updateClusterFootprints - Function to update the cluster footprints.
 * @property {(clusterFootprints: ClusterFootprint[]) => void} updateSelectedClusterFootprints - Function to update the selected cluster footprints.
 * @property {(period: Period) => void} updatePeriod - Function to update the period.
 */
export interface FootprintContextStruct {
  period: string;
  currentClusterFootprints: ClusterFootprint;
  selectedClusterFootprints: ClusterFootprint[];
  allClusterFootprints: ClusterFootprint[];
  currentCarbonConsumption: ClusterConsumption | undefined;
  currentEnergyConsumption: ClusterConsumption | undefined;
  currentCostConsumption: ClusterConsumption | undefined;
  updateClusterFootprints: (fullname: string) => void;
  updateSelectedClusterFootprints: (clusterFootprints: ClusterFootprint[]) => void;
  updatePeriod: (period: Period) => void;
}
