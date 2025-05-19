import {ClusterDescription, ClusterOverview} from "../frugalit/slices/api.tsx";
import {DurationPrecision} from "../utils/period.tsx";

/**
 * The Application context keeps track of all the clusters known to frugal IT.
 * If a cluster is selected as the current cluster, its namespaces will be
 * loaded. 
 * 
 * These two levels cluster and namespaces are shared among components. 
 */
export interface ApplicationContextStruct {
    /**
     * The currently selected cluster overview. It displays only the identification information
     * of the current cluster.
     */
    currentClusterOverview: ClusterOverview;

    /**
     * The details of the currently selected cluster. It contains more detailed information
     * such as the list of namespaces each with the list of resources.
     */
    currentClusterDescription: ClusterDescription;
  
    /**
     * A list of all available clusters.
     */
    allClusters: ClusterOverview[];
  
    /**
     * The list of namespaces from the currently selected cluster.
     */
    currentNamespaces: string[];
  
    /**
     * A list of selected namespaces.
     * @todo: This must be moved to the Inspect page component.
     */
    selectedNamespaces: string[];
  
    /**
     * The current precision setting (e.g. seconds, minutes, hours, etc.).
     */
    currentPrecision: DurationPrecision;
  
    /**
     * Updates the currently selected cluster.
     * @param cluster The new cluster to select.
     */
    updateCurrentCluster: (cluster: ClusterOverview) => void;
  
    /**
     * Updates the list of all available clusters.
     * @param clusters The new list of clusters.
     */
    updateAllClusters: (clusters: ClusterOverview[]) => void;
  
    /**
     * Updates the list of selected namespaces.
     * @param namespace The new list of selected namespaces.
     */
    updateSelectedNamespaces: (namespace: string[]) => void;
  
    /**
     * Adds or removes a single namespace from the list of selected namespaces.
     * @param namespace The namespace to add or remove.
     */
    updateSingleNamespace: (namespace: string) => void;
  
    /**
     * Updates the current precision setting.
     * @param precision The new precision setting.
     */
    updateCurrentPrecision: (precision: DurationPrecision) => void;
  
    /**
     * Fetches data for a specific cluster and its namespaces.
     * @param clusterFullName The full name of the cluster to fetch data for.
     */
    fetchClusterAndNamespaceData: (clusterFullName: string) => Promise<void>;
    /**
     * Whether the sidebar is collapsed or not.
     */
    isSidebarCollapsed: boolean;

    /**
     * Whether the application is in dark mode or not.
     */
    darkMode: boolean;

    /**
     * Toggles the sidebar collapsed state.
     */
    toggleSidebar: () => void;

    /**
     * Toggles between dark and light mode.
     */
    toggleDarkMode: () => void;
  }