import { useEffect, useContext } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageBodyWrapper } from "../../common/PageBodyWrapper.tsx";
import { ExplainContext } from '../../app/ExplainContextProvider.tsx';
import { ApplicationContext } from '../../app/ApplicationContextProvider.tsx';
import LoadingWithProgress from '../../components/LoadingWithProgress.tsx';
import { ClusterDescription } from '../slices/api.tsx';
import { WorkloadCard } from '../component/WorkloadCard.tsx';

export const ExplainWorkload = () => {
    const [searchParams] = useSearchParams();
    const clusterFullName = searchParams.get("cluster");
    const namespace = searchParams.get("namespace");
    const workload = searchParams.get("workload");
    const applicationContext = useContext(ApplicationContext);
    const { currentClusterDescription, currentClusterOverview } = useContext(ApplicationContext);
    const explainContext = useContext(ExplainContext); // Access ExplainContext

    // Fetch the resource when the parameters change.
    useEffect(() => {
        if (!currentClusterDescription || !currentClusterOverview) {
            if (clusterFullName) {
                applicationContext.fetchClusterAndNamespaceData(clusterFullName);  // Load the cluster details
            }
        }
        // Check if the correct cluster, namespace, and resource are selected in the ExplainContext
        if (currentClusterDescription && currentClusterOverview && currentClusterOverview.fullname === clusterFullName
            && namespace && workload) {
            const resourceKind = getResourceKind(currentClusterDescription, namespace, workload);
            if (resourceKind) {
                explainContext.loadResource(currentClusterOverview.fullname, namespace, workload, resourceKind);  // Trigger loading of the resource
            }
        }
    }, [currentClusterDescription, currentClusterOverview, clusterFullName, namespace, workload]); // Re-run when params or cluster overview change

    if (!currentClusterOverview || currentClusterOverview?.fullname !== clusterFullName) {
        return <PageBodyWrapper><LoadingWithProgress /></PageBodyWrapper>;
    }
    // Guard: If resource data is missing in the ExplainContext, show a loading spinner.
    if (
        !explainContext?.resource ||
        !explainContext?.essentials ||
        !explainContext?.id ||
        !explainContext?.score ||
        !explainContext?.advanced ||
        !explainContext?.factList
    ) {
        return (
            <PageBodyWrapper>
                <LoadingWithProgress />
            </PageBodyWrapper>
        );
    }
    // Render the resource details when everything is loaded.
    return (
        <PageBodyWrapper>
            <WorkloadCard
                cluster={currentClusterOverview}
                namespace={explainContext.currentNamespace}
                id={explainContext.id}
                score={explainContext.score}
                factList={explainContext.factList}
                advanced={explainContext.advanced?.data}
                essentials={explainContext.essentials}
                summary={explainContext.summary}
                resource={explainContext.resource}
            />
        </PageBodyWrapper>
    );
};

const getResourceKind = (clusterDescription: ClusterDescription, namespaceName: string, resourceName: string): string | undefined => {
    // Find the namespace that matches the provided namespaceName
    const namespace = clusterDescription.namespaces.find(ns => ns.name === namespaceName);

    // If the namespace is found, find the resource with the matching resourceName
    if (namespace) {
        const resource = namespace.workloads.find(res => res.name === resourceName);
        // If the resource is found, return its kind
        if (resource) {
            return resource.kind;
        }
    }

    // If no matching namespace or resource is found, return undefined
    return undefined;
};
