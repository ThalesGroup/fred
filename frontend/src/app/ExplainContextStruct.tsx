import { Workload } from "../utils/resource.tsx";
import { WorkloadAdvanced, WorkloadId, WorkloadEssentials } from "../slices/api.tsx";
import { FactList } from "../slices/factsStructures.tsx";
import { WorkloadSummary } from "../slices/workloadSummaryStructures.tsx";
import { WorkloadScores } from "../slices/scoresStructures.tsx";

/**
 * The ExplainContextStruct contains the current resource that are being explained. 
 * This structure is not perfect it actually is only good to represent a deployment
 * or statefulset. 
 */
export interface ExplainContextStruct {
  /**
   * The current resource being displayed.
   */
  resource: Workload;

  /**
   * The current namespace being displayed.
   */
  currentNamespace: string;

  /**
   * The essentials information of the current resource.
   */
  summary: WorkloadSummary;

  /**
   * The essentials information of the current resource.
   */
  essentials: WorkloadEssentials;

  /**
   * The advanced information of the current resource.
   */
  advanced: WorkloadAdvanced;

  /**
   * The application information of the current resource.
   */
  id: WorkloadId;

  /**
   * The score information of the current resource.
   */
  score: WorkloadScores;

  /**
   * The facts information of the current resource.
   */
  factList: FactList;

  /**
* Load the resource data including essentials, advanced, application, score, and facts.
* @param clusterName The name of the cluster.
* @param namespace The name of the namespace.
* @param resourceName The name of the resource.
*/
  loadResource: (clusterName: string, namespace: string, resourceName: string, resourceKind: string) => Promise<void>;

}
