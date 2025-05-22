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

import {ClusterConsumption} from "../frugalit/slices/api.tsx";

export interface SeriePoint {
  date: string;
  value: number;
}

// Serie interface used for bar and line charts
export interface Serie {
  name: string;
  color: string;
  unit: string;
  seriePoints: SeriePoint[];
}

// Returns the mean value of serie in the given array
export const getMeanValue = (serie: Serie): number => {
  if (!serie.seriePoints) return 0;
  return Math.round(serie.seriePoints.reduce((sum, { value }) => sum + value, 0) / serie.seriePoints.length);
};

// Returns the maximum value of serie in the given array
export const getMaxValue = (series: Serie[]): number => {
  if (!Array.isArray(series)) return 0;
  return series.reduce((globalMax, serie) => {
    if (!serie.seriePoints || serie.seriePoints.length === 0) return globalMax;
    const serieMax = serie.seriePoints.reduce((max, { value }) => Math.max(max, value), serie.seriePoints[0].value);
    return Math.max(globalMax, serieMax);
  }, 0);
};

// Returns the minimum value of serie in the given array
export const getMinValue = (serie: Serie): number => {
  if (!serie.seriePoints) return 0;
  return serie.seriePoints.reduce((max, { value }) => Math.min(max, value), serie.seriePoints[0] ? serie.seriePoints[0].value : 0)
};

// Returns the sum of values in the given array
export const getSumValue = (serie: Serie): number => {
  if (!serie.seriePoints) return 0;
  return parseFloat(serie.seriePoints.reduce((sum, { value }) => sum + value, 0).toFixed(0));
};

// Returns a Serie Object from a ClusterConsumption Object
export const transformClusterConsumptionToSerie = (
  clusterConsumptionArray: ClusterConsumption,
  name: string,
  color: string,
): Serie => {
  return {
    name: name,
    color: color,
    unit: clusterConsumptionArray.unit,
    seriePoints: clusterConsumptionArray.values.map((value, index) => ({
      date: clusterConsumptionArray.timestamps[index],
      value: Math.round(value * 100) / 100,
    }))
  };
};