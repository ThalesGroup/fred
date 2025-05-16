import { useContext, useEffect } from 'react';
import { ApplicationContext } from '../app/ApplicationContextProvider';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { Skeleton } from '@mui/material';
import { PageBodyWrapper } from '../common/PageBodyWrapper';

const withClusterSync = (Component) => {
  return (props) => {
    const navigate = useNavigate();
    const location = useLocation();
    const { currentClusterOverview } = useContext(ApplicationContext);
    const { clusterName } = useParams();

    useEffect(() => {
      if (currentClusterOverview?.alias !== clusterName) {
        // Replace the current clusterName in the URL with the new one
        const updatedPath = location.pathname.replace(clusterName, currentClusterOverview?.alias);
        navigate(updatedPath);
      }
    }, [clusterName, currentClusterOverview, location.pathname, navigate]);

    if (!currentClusterOverview || currentClusterOverview?.alias !== clusterName) {
      return (
        <PageBodyWrapper>
          <Skeleton animation="wave" width={"80%"} height={"200px"} />
        </PageBodyWrapper>
      );
    }

    return <Component {...props} />;
  };
};

export default withClusterSync;
