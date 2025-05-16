/**
 * Debug component that displays the current cluster overview.
 * 
 * This component uses the `useNavigate` hook from `react-router-dom` to navigate
 * to the correct cluster overview page if the `clusterName` from the URL parameters
 * does not match the `alias` of the `currentClusterOverview` from the application context.
 * 
 * If the `currentClusterOverview` is not available or the `alias` does not match the `clusterName`,
 * a loading skeleton is displayed.
 * 
 * @component
 * @returns {JSX.Element} The rendered component.
 * 
 * @example
 * ```tsx
 * import Debug from './Debug';
 * 
 * function App() {
 *   return (
 *     <Debug />
 *   );
 * }
 * ```
 */
import { useContext, useEffect } from 'react';
import { ApplicationContext } from '../app/ApplicationContextProvider';
import { useNavigate, useParams } from 'react-router-dom';
import { PageBodyWrapper } from '../common/PageBodyWrapper';
import LoadingWithProgress from '../components/LoadingWithProgress';

const Debug = () => {
    const navigate = useNavigate();
    const { currentClusterOverview } = useContext(ApplicationContext);
    const { clusterName } = useParams();
   
    // Check if the current cluster overview is available and the alias matches the clusterName
    // If not, navigate to the correct cluster overview page. This is typically used to sync the URL
    // with the current cluster overview in the application context  after a side bar change.
    useEffect(() => {
        if (currentClusterOverview?.alias !== clusterName) {
            navigate(`/debug/${currentClusterOverview?.alias}`, { replace: true });
        }
    }, [clusterName, currentClusterOverview]);

    if (!currentClusterOverview || currentClusterOverview?.alias !== clusterName) {
        return <PageBodyWrapper><LoadingWithProgress /></PageBodyWrapper>;
    }

    return (
        <PageBodyWrapper>
            <h1>DEBUG PAGE </h1>
            <h2>Cluster Name: {currentClusterOverview.alias}</h2>
        </PageBodyWrapper>
    );
};
export default Debug;
