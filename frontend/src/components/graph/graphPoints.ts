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

import { useEffect, useState } from "react";
import { GraphPoint } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";

// Sync local points with latest projection and manage a fitVersion counter
export function usePointsSync(graphPoints: GraphPoint[] | undefined, isProjecting: boolean) {
  const [points, setPoints] = useState<GraphPoint[]>([]);
  const [fitVersion, setFitVersion] = useState(0);

  useEffect(() => {
    if (graphPoints && graphPoints.length) {
      setPoints(graphPoints);
      setFitVersion((v) => v + 1); // trigger fit on new projection
    } else if (!isProjecting) {
      setPoints([]);
    }
  }, [graphPoints, isProjecting]);

  return { points, setPoints, fitVersion } as const;
}
