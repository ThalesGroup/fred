import { useEffect } from "react";

import { PageBodyWrapper } from "../../common/PageBodyWrapper.tsx";
import { TopBar } from "../../common/TopBar.tsx";

import { GeomapLayout } from '../component/Geomap.tsx';
import { useGetTheaterOfOperationMapDataMutation } from '../../frugalit/slices/api.tsx'; 

export const Geomap = () => {
  const [getTheaterOfOperationMapData, { data, isLoading, isError }] = useGetTheaterOfOperationMapDataMutation();

  useEffect(() => {
    getTheaterOfOperationMapData();
  }, [getTheaterOfOperationMapData]);

  return (
    <PageBodyWrapper>
      <TopBar
        title="Theater of Operations"
        description="Navigate the current theater of operations from data captured in the Mediterranean Sea near the maritime neighbourhood TL."
        backgroundUrl=""
        leftLg={4}
      />

      {isLoading && <div>Loading map data...</div>}
      {isError && <div>Error loading map data.</div>}
      {data && <GeomapLayout data={data} />}
    </PageBodyWrapper>
  );
};
