import { createContext, PropsWithChildren, useState } from "react";
import { ExplainContextStruct } from "./ExplainContextStruct.tsx";
import {
    WorkloadAdvanced,
    WorkloadId,
    WorkloadEssentials,
    useGetWorkloadFactsMutation,
    useGetWorkloadScoreMutation,
    useGetWorkloadSummaryMutation,
    useGetWorkloadAdvancedMutation,
    useGetWorkloadEssentialsMutation,
    useGetWorkloadIdMutation,
} from "../frugalit/slices/api.tsx";
import { Workload } from "../utils/resource.tsx";
import { createFactList, FactList } from "../frugalit/slices/factsStructures.tsx";
import { WorkloadSummary } from "../frugalit/slices/workloadSummaryStructures.tsx";
import { WorkloadScores } from "../frugalit/slices/scoresStructures.tsx";

export const ExplainContext = createContext<ExplainContextStruct>(null!);

// Helper function to centralize resource data fetching
async function fetchResourceDetails({
    resourceName,
    kind,
    namespace,
    cluster,
    getSummary,
    getEssentials,
    getAdvanced,
    getApplication,
    getScore,
    getFacts
}) {
    console.log("Fetching resource details", resourceName, namespace, cluster, kind);
    const [summaryRes, essentialsRes, advancedRes, applicationRes, scoreRes,
        factsRes
    ] = await Promise.all([
        getSummary({ cluster: cluster, namespace: namespace, workload: resourceName, kind: kind }),
        getEssentials({ cluster: cluster, namespace: namespace, workload: resourceName, kind: kind }),
        getAdvanced({ cluster: cluster, namespace: namespace, workload: resourceName, kind: kind }),
        getApplication({ cluster: cluster, namespace: namespace, workload: resourceName, kind: kind }),
        getScore({ cluster: cluster, namespace: namespace, workload: resourceName, kind: kind }),
        getFacts({ cluster: cluster, namespace: namespace, workload: resourceName, kind: kind }),
    ]);

    const summary = summaryRes.data || {};
    const essentials = essentialsRes.data || {};
    const advanced = advancedRes.data || {};
    const id = applicationRes.data || {};
    const score = scoreRes.data || {};
    const facts = factsRes.data || [];
    return {
        summary, essentials, advanced, id, score, facts
    };
}

export const ExplainContextProvider = (props: PropsWithChildren<{}>) => {
    const [getWorkloadSummary] = useGetWorkloadSummaryMutation();
    const [getWorkloadEssentials] = useGetWorkloadEssentialsMutation();
    const [getWorkloadAdvanced] = useGetWorkloadAdvancedMutation();
    const [getWorkloadApplication] = useGetWorkloadIdMutation();
    const [getWorkloadScore] = useGetWorkloadScoreMutation();
    const [getWorkloadFacts] = useGetWorkloadFactsMutation();

    const [currentNamespace] = useState<string | undefined>(undefined);
    const [resource, setResource] = useState<Workload | undefined>(undefined);
    const [resourceEssentials, setResourceEssentials] = useState<WorkloadEssentials | undefined>(undefined);
    const [resourceSummary, setResourceSummary] = useState<WorkloadSummary | undefined>(undefined);
    const [resourceAdvanced, setResourceAdvanced] = useState<WorkloadAdvanced | undefined>(undefined);
    const [resourceApplication, setResourceApplication] = useState<WorkloadId | undefined>(undefined);
    const [resourceScore, setResourceScore] = useState<WorkloadScores | undefined>(undefined);
    const [resourceFacts, setResourceFacts] = useState<FactList | undefined>(undefined);

    // Simplified function to load resource details based on current cluster, namespace, and resource name
    const loadResource = async (clusterName: string, namespace: string, resourceName: string, resourceKind: string) => {

        console.log("Loading resource", resourceName, namespace, clusterName, resourceKind);
        // Clear current resource data
        setResource(undefined);
        setResourceSummary(undefined);
        setResourceEssentials(undefined);
        setResourceAdvanced(undefined);
        setResourceApplication(undefined);
        setResourceScore(undefined);
        setResourceFacts(createFactList());
        const fetcher = {
            getSummary: getWorkloadSummary,
            getEssentials: getWorkloadEssentials,
            getAdvanced: getWorkloadAdvanced,
            getApplication: getWorkloadApplication,
            getScore: getWorkloadScore,
            getFacts: getWorkloadFacts
        };
        const { summary, essentials, advanced, id, score, facts, 
        } = await fetchResourceDetails({
            resourceName: resourceName,
            namespace: namespace,
            cluster: clusterName,
            kind: resourceKind,
            ...fetcher,
        });
        setResourceSummary(summary);
        setResourceEssentials(essentials);
        setResourceAdvanced(advanced);
        setResourceApplication(id);
        setResourceScore(score);
        setResourceFacts(facts);
        setResource({
            name: resourceName,
            namespace: namespace,
            kind: resourceKind,
        });
    };

    // Context value provided to the ExplainContext consumers
    const contextValue: ExplainContextStruct = {
        resource,
        currentNamespace,
        essentials: resourceEssentials,
        advanced: resourceAdvanced,
        summary: resourceSummary,
        id: resourceApplication,
        score: resourceScore,
        factList: resourceFacts,
        loadResource, // New method to load resource
    };
    console.log("ExplainContextProvider", contextValue);
    return <ExplainContext.Provider value={contextValue}>{props.children}</ExplainContext.Provider>;
};
