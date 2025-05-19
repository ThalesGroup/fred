export interface ClusterSummary {
    cluster_summary: string,
}

// Define default values for Essentials
const defaultClusterSummary: ClusterSummary = {
    cluster_summary: "none",
};

/**
 * Create an Essentials object with default values.
 * @param props Partial<Essentials> with fields to override in the default Essentials object.
 * @returns An Essentials object with the default values overridden by any provided props.
 */
export function createClusterSummary(props: Partial<ClusterSummary> = {}): ClusterSummary {
    return { ...defaultClusterSummary, ...props };
}