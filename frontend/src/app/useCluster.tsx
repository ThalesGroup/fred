import { useContext, useEffect, useState } from "react";
import { ApplicationContext } from "../app/ApplicationContextProvider.tsx";

/**
 * Custom hook to fetch cluster and namespace data
 * @param clusterName The name of the cluster to fetch data for
 */
export const useCluster = (clusterName: string | undefined) => {
  const global_context = useContext(ApplicationContext);
  const [isFetching, setIsFetching] = useState(false); // Add a fetching flag to prevent redundant fetches

  useEffect(() => {
    if (clusterName && !isFetching) {
      // Check if the clusterName is already the current cluster to avoid re-fetching
      if (global_context.currentClusterOverview?.alias === clusterName) {
        return;
      }

      console.log("Fetching data for cluster", clusterName);
      setIsFetching(true); // Mark as fetching to avoid multiple fetches

      // Call fetchClusterAndNamespaceData and use .finally()
      global_context.fetchClusterAndNamespaceData(clusterName)
        .finally(() => {
          setIsFetching(false); // Reset fetching flag when done
        });
    }
  }, [clusterName, global_context]); // Ensure the effect only triggers when the clusterName changes
};
