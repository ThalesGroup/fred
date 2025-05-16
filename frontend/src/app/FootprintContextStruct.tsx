import {Period} from "../utils/period.tsx";
import {ClusterConsumption, ClusterFootprint} from "../slices/api.tsx";
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
