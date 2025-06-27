// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useEffect } from "react";

import { TopBar } from "../../common/TopBar.tsx";

import { GeomapLayout } from "../component/Geomap.tsx";
import { useGetTheaterOfOperationMapDataMutation } from "../../frugalit/slices/api.tsx";

export const Geomap = () => {
  const [getTheaterOfOperationMapData, { data, isLoading, isError }] = useGetTheaterOfOperationMapDataMutation();

  useEffect(() => {
    getTheaterOfOperationMapData();
  }, [getTheaterOfOperationMapData]);

  return (
    <>
      <TopBar
        title="Theater of Operations"
        description="Navigate the current theater of operations from data captured in the Mediterranean Sea near the maritime neighbourhood TL."
        leftLg={4}
      />

      {isLoading && <div>Loading map data...</div>}
      {isError && <div>Error loading map data.</div>}
      {data && <GeomapLayout data={data} />}
    </>
  );
};
