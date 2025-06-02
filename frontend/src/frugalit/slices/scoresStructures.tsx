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

export interface ClusterScores {
  cluster: string;
  namespaces: NamespaceScore[];
}

export interface NamespaceScore {
  namespace: string;
}

// Define the structure for individual resource attributes
export interface ScoreAttribute {
  score: number;
  reason: string;
}

// Define the Score interface with dynamic keys. A workload score is a mapping of resource attributes to their scores.
// It is returned by the backend as part of the cluster scores and independently for each workload
export interface WorkloadScores {
  [key: string]: ScoreAttribute; // This allows for dynamic keys (e.g., 'cpu', 'ram', etc.)
}

// Define default values for Score
const defaultWorkloadScores: WorkloadScores = {};

/**
 * Create a Score object with default values.
 * @param props Partial<Score> with fields to override in the default Score object.
 * @returns A Score object with the default values overridden by any provided props.
 */
export function createScores(props: Partial<WorkloadScores> = {}): WorkloadScores {
  return { ...defaultWorkloadScores, ...props };
}

export interface Workload {
  name: string; // Workload name (e.g., "elk-errors-indexing")
  namespace: string; // Namespace of the workload (e.g., "applicative")
  kind: string; // Workload type (e.g., "Deployment")
  scores: WorkloadScores; // Scores for the workload attributes
}

export interface ClusterScore {
  cluster: string; // ARN or identifier for the cluster
  alias: string; // Human-readable alias for the cluster
  workload_scores: Workload[]; // Array of workloads and their associated scores
}
