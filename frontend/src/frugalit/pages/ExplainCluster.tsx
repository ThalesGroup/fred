import { useSearchParams } from 'react-router-dom';
import { PageBodyWrapper } from "../../common/PageBodyWrapper.tsx";
import { Box } from '@mui/material';
import { useContext, useEffect, useState } from 'react';
import { ApplicationContext } from '../../app/ApplicationContextProvider.tsx';
import { ClusterCard } from '../component/ClusterCard.tsx';
import { createFactList, FactList } from '../slices/factsStructures.tsx';
import { useGetClusterFactsMutation, useGetClusterSummaryMutation } from '../slices/api.tsx';
import { ClusterSummary } from '../component/clusterSummaryStructures.tsx';
import LoadingWithProgress from '../../components/LoadingWithProgress.tsx';

async function fetchClusterDescription({
    cluster,
    getSummary,
    getFacts,
}) {
    const [summaryRes, factsRes] = await Promise.all([
        getSummary({ cluster: cluster }),
        getFacts({ cluster: cluster }),
    ]);
    const summary = summaryRes.data || {};
    const facts = factsRes.data || [];
    return { summary, facts };
}

export const ExplainCluster = () => {
    const [searchParams] = useSearchParams();
    const clusterFullName = searchParams.get("cluster");
    const [getClusterSummary] = useGetClusterSummaryMutation();
    const [getClusterFacts] = useGetClusterFactsMutation();
    const { currentClusterOverview } = useContext(ApplicationContext);
    const [clusterFacts, setClusterFacts] = useState<FactList | undefined>(undefined);
    const [clusterSummary, setClusterSummary] = useState<ClusterSummary | undefined>(undefined);
    const applicationContext = useContext(ApplicationContext);
    
    const loadClusterData = async (clusterFullName: string) => {
        // Clear current resource data
        setClusterSummary(clusterSummary);
        setClusterFacts(createFactList());
        const fetcher = {
            getSummary: getClusterSummary,
            getFacts: getClusterFacts,
        };
        const { summary, facts,
        } = await fetchClusterDescription({
            cluster: clusterFullName,
            ...fetcher,
        });
        setClusterFacts(facts);
        setClusterSummary(summary);
    };
    useEffect(() => {
        if (currentClusterOverview) {
            loadClusterData(clusterFullName);
        } else {
            applicationContext.fetchClusterAndNamespaceData(clusterFullName);
        }
    }, [clusterFullName, currentClusterOverview]); // Trigger when 'cluster' changes

    if (!currentClusterOverview || currentClusterOverview?.fullname !== clusterFullName) {
        return <PageBodyWrapper><LoadingWithProgress /></PageBodyWrapper>;
    }
    console.log("ExplainCluster: facts", clusterFacts);
    return (
        <PageBodyWrapper>
            <Box
                display="flex"
                flexDirection="column"
                justifyContent="center"
                alignItems="center"
                minHeight="50vh"
            >
                <ClusterCard cluster={currentClusterOverview} factList={clusterFacts} summary={clusterSummary} />
            </Box>
        </PageBodyWrapper>
    );
};
