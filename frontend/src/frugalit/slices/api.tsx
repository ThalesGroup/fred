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

import { createApi } from '@reduxjs/toolkit/query/react';
import { WorkloadNameList } from "../../utils/resource.tsx";
import { NamespaceList } from "../../utils/namespace.tsx";
import { Fact, FactList } from './factsStructures.tsx';
import { Ship, ShipList } from '../../warfare/slices/shipStructures.tsx';
import { ClusterSummary } from '../component/clusterSummaryStructures.tsx';
import { NamespaceSummary } from './namespaceSummaryStructures.tsx';
import { WorkloadSummary } from './workloadSummaryStructures.tsx';
import { ClusterScore, WorkloadScores } from './scoresStructures.tsx';
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery.tsx";

export interface ResourceKind {
    kind: string
}

export interface WorkloadDescription {
    name: string
    kind: string
    facts: Fact[]
}

export interface NamespaceDescription {
    name: string
    workloads: WorkloadDescription[]
    facts: Fact[]
}

export interface FileUploadStatus {
    filename: string;
    status: "uploaded" | "failed";
    document_uid?: string;
    error?: string;
}

export interface UploadDocumentsResponse {
    results: FileUploadStatus[];
}

// A cluster details is a list of resources that are part of a cluster.
// It is used to display the detailed information in the UI when a user
// clicks on a cluster.
export interface ClusterDescription {
    cluster: string
    alias: string
    namespaces: NamespaceDescription[]
    facts: Fact[]
}

// A cluster is a group of resources that are managed together. For example, a cluster could be a Kubernetes cluster.
// It is the highest level of abstraction in the frugal-it data model.
// The cluster overview is short and is meant to be returned as part of discovering many 
// clusters (possibly thousands of clusters).
export interface ClusterOverview {
    sensor: string,
    fullname: string,
    alias: string,
    region: string,
    provider: string,
}

// A cluster footprint is a cluster with additional information about its cost,
// carbon footprint and energy consumption. It is used to display the
// overview information in the UI top level views.
export interface ClusterFootprint {
    cluster: ClusterOverview,
    cost: {
        value: number,
        unit: string
    },
    carbon: {
        value: number,
        unit: string
    },
    energy: {
        value: number,
        unit: string
    }
}

// Each resource in a cluster that is understood by the frugal-it AI assistant
// is associated with some information. The Essentials class describes the
// basic information that is associated with a resource.
export interface WorkloadEssentials {
    name: string,
    namespace: string,
    kind: string,
    container_image: string,
    version: string,
    replicas: number
}

export interface VectorizeResponse {
    status: string;
    message: string;
    ignored_documents: string[];
    ignored_documents_count: number;
}

export interface ContextCard {
    id?: string;
    title: string;
    content: string;
}


// Define default values for Essentials
const defaultWorkloadEssentials: WorkloadEssentials = {
    name: "undefined",
    namespace: "undefined",
    kind: "undefined",
    container_image: "undefined",
    version: "undefined",
    replicas: -1,
};

/**
 * Create an Essentials object with default values.
 * @param props Partial<Essentials> with fields to override in the default Essentials object.
 * @returns An Essentials object with the default values overridden by any provided props.
 */
export function createWorkloadEssentials(props: Partial<WorkloadEssentials> = {}): WorkloadEssentials {
    return { ...defaultWorkloadEssentials, ...props };
}

// The Advanced class describes the advanced information that is associated
// with a resource.
export type WorkloadAdvanced = Record<string, any>;

const defaultWorkloadAdvanced: WorkloadAdvanced = {}

/**
 * Create an Advanced object with default values.
 * @param props Partial<Advanced> with fields to override in the default Advanced object.
 * @returns An Advanced object with the default values overridden by any provided props.
 */
export function createWorkloadAdvanced(props: Partial<WorkloadAdvanced> = {}): WorkloadAdvanced {
    return { ...defaultWorkloadAdvanced, ...props };
}

// The Application class describes the guessed application fundamental
// information that is associated with a resource. For example 'Kafka'
// that will be deduced possibly from a container image name.
export interface WorkloadId {
    workload_id: string,
}

const defaultWorkloadId: WorkloadId = {
    workload_id: "undefined",
};

export function createWorkloadId(props: Partial<WorkloadId> = {}): WorkloadId {
    return { ...defaultWorkloadId, ...props };
}

// A Cluster Consumption object is a time series of values that represent
// the consumption of a cluster over time. The timestamps are in ISO8601.
// Note that in the current frugal-it version a cluster is a cluster.
export interface ClusterConsumption {
    timestamps: string[];
    values: number[];
    auc: number;
    unit: string;
    details?: Detail[]
}

// TODO change the name of this interface it means nothing.
export interface Detail {
    name: string;
    kind: string;
    values: number[];
}

// Base API slice definition
export const apiSlice = createApi({
    reducerPath: 'api',  // Optional: Defines where the slice is added to the state
    baseQuery: createDynamicBaseQuery({ backend: "api" }),
    endpoints: () => ({}),
});

// Export the API slice reducer and middleware
export const { reducer: apiReducer, middleware: apiMiddleware } = apiSlice;

const extendedApi = apiSlice.injectEndpoints({
    endpoints: (builder) => ({
        getTheaterOfOperationMapData: builder.mutation<ShipList, void>({
            query: () => ({
                url: `/fred/guerre_elec/active_ships`,
                method: 'GET',
            }),
            transformResponse: (raw: { details: Ship[] }) => {
                return { ships: raw.details };
            },
        }),
        getCarbonConsumption: builder.mutation<ClusterConsumption, {
            start: string;
            end: string,
            cluster: string,
            precision: string
        }>({
            query: ({ start, end, cluster, precision }: {
                start: string;
                end: string;
                cluster: string,
                precision: string | null
            }) => ({
                url: `/fred/carbon/consumption/?start=${start}&end=${end}&cluster=${cluster}&precision=${precision ? precision : 'T'}`,
                method: 'GET',
            }),
        }),
        getEnergyConsumption: builder.mutation<ClusterConsumption, {
            start: string;
            end: string,
            cluster: string,
            precision: string
        }>({
            query: ({ start, end, cluster, precision }: {
                start: string;
                end: string;
                cluster: string,
                precision: string | null
            }) => ({
                url: `/fred/energy/consumption/?start=${start}&end=${end}&cluster=${cluster}&precision=${precision ? precision : 'T'}`,
                method: 'GET',
            }),
        }),
        getEnergyMix: builder.mutation<ClusterConsumption, {
            start: string;
            end: string,
            cluster: string,
            precision: string
        }>({
            query: ({ start, end, cluster, precision }: {
                start: string;
                end: string;
                cluster: string,
                precision: string | null
            }) => ({
                url: `/fred/energy/mix/?start=${start}&end=${end}&cluster=${cluster}&precision=${precision ? precision : 'T'}`,
                method: 'GET',
            }),
        }),
        getFinopsCost: builder.mutation<ClusterConsumption, {
            start: string;
            end: string,
            cluster: string,
            precision: string
        }>({
            query: ({ start, end, cluster, precision }: {
                start: string;
                end: string;
                cluster: string,
                precision: string | null
            }) => ({
                url: `/fred/finops/cloud-cost/?start=${start}&end=${end}&cluster=${cluster}&precision=${precision ? precision : 'T'}`,
                method: 'GET',
            }),
        }),
        getClusterList: builder.mutation<ClusterOverview[], void>({
            query: () => ({
                url: `/fred/kube/clusters`,
                method: 'GET',
            }),
        }),
        getClusterDescription: builder.mutation<ClusterDescription, { cluster: string }>({
            query: ({ cluster }: { cluster: string }) => ({
                url: `/fred/ui/details?cluster_name=${cluster}`,
                method: 'GET',
            }),
        }),
        getClusterScores: builder.mutation<ClusterScore, { cluster: string }>({
            query: ({ cluster }: { cluster: string }) => ({
                url: `/fred/ui/scores?cluster_name=${cluster}`,
                method: 'GET',
            }),
        }),
        getClustersFootprints: builder.mutation<ClusterFootprint[], { start: string; end: string }>({
            query: ({ start, end }: { start: string; end: string }) => ({
                url: `/fred/clusters/footprints?start=${start}&end=${end}`,
                method: 'GET',
            }),

        }),
        getNamespaceList: builder.mutation<NamespaceList, { cluster: string }>({
            query: ({ cluster }: { cluster: string }) => ({
                url: `/fred/kube/namespaces?cluster_name=${cluster}`,
                method: 'GET',
            }),
        }),
        GetWorkloadList: builder.mutation<WorkloadNameList, { cluster: string, namespace: string }>({
            query: ({ cluster, namespace }: { cluster: string, namespace: string }) => ({
                url: `/fred/kube/workloads?cluster_name=${cluster}&namespace=${namespace}`,
                method: 'GET',
            }),
        }),
        GetWorkloadSummary: builder.mutation<WorkloadSummary, {
            cluster: string,
            namespace: string,
            workload: string,
            kind: string

        }>({
            query: ({ cluster, namespace, workload, kind }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string
            }) => ({
                url: `/fred/ai/workload/summary?kind=${kind}&cluster_name=${cluster}&namespace=${namespace}&workload_name=${workload}`,
                method: 'GET',
            }),
        }),
        GetClusterSummary: builder.mutation<ClusterSummary, {
            cluster: string,
        }>({
            query: ({ cluster }: {
                cluster: string,
            }) => ({
                url: `/fred/ai/cluster/summary?cluster_name=${cluster}`,
                method: 'GET',
            }),
        }),
        GetNamespaceSummary: builder.mutation<NamespaceSummary, {
            cluster: string,
            namespace: string,
        }>({
            query: ({ cluster, namespace }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string
            }) => ({
                url: `/fred/ai/namespace/summary?cluster_name=${cluster}&namespace=${namespace}`,
                method: 'GET',
            }),
        }),
        GetWorkloadEssentials: builder.mutation<WorkloadEssentials, {
            cluster: string,
            namespace: string,
            workload: string,
            kind: string
        }>({
            query: ({ cluster, namespace, workload, kind }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string
            }) => ({
                url: `/fred/ai/workload/essentials?kind=${kind}&cluster_name=${cluster}&namespace=${namespace}&workload_name=${workload}`,
                method: 'GET',
            }),
        }),
        GetWorkloadAdvanced: builder.mutation<WorkloadAdvanced, {
            cluster: string,
            namespace: string,
            workload: string,
            kind: string
        }>({
            query: ({ cluster, namespace, workload, kind }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string
            }) => ({
                url: `/fred/ai/workload/advanced?kind=${kind}&cluster_name=${cluster}&namespace=${namespace}&workload_name=${workload}`,
                method: 'GET',
            }),
        }),
        GetWorkloadId: builder.mutation<WorkloadId, {
            cluster: string,
            namespace: string,
            workload: string,
            kind: string
        }>({
            query: ({ cluster, namespace, workload, kind }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string
            }) => ({
                url: `/fred/ai/workload/id?kind=${kind}&cluster_name=${cluster}&namespace=${namespace}&workload_name=${workload}`,
                method: 'GET',
            }),
        }),
        GetWorkloadScore: builder.mutation<WorkloadScores, {
            cluster: string, namespace: string,
            workload: string,
            kind: string
        }>({
            query: ({ cluster, namespace, workload, kind }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string
            }) => ({
                url: `/fred/ai/workload/scores?kind=${kind}&cluster_name=${cluster}&namespace=${namespace}&workload_name=${workload}`,
                method: 'GET',
            }),
        }),

        GetWorkloadFacts: builder.mutation<FactList, {
            cluster: string,
            namespace: string,
            workload: string,
            kind: string
        }>({
            query: ({ cluster, namespace, workload, kind }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string
            }) => ({
                url: `/fred/ai/workload/facts?kind=${kind}&cluster_name=${cluster}&namespace=${namespace}&workload_name=${workload}`,
                method: 'GET',
            })
        }),
        GetNamespaceFacts: builder.mutation<FactList, { cluster: string, namespace: string }>({
            query: ({ cluster, namespace }: {
                cluster: string,
                namespace: string
            }) => ({
                url: `/fred/ai/namespace/facts?cluster_name=${cluster}&namespace=${namespace}`,
                method: 'GET',
            })
        }),
        GetClusterFacts: builder.mutation<FactList, { cluster: string }>({
            query: ({ cluster }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string
            }) => ({
                url: `/fred/ai/cluster/facts?cluster_name=${cluster}`,
                method: 'GET',
            })
        }),
        postWorkloadFacts: builder.mutation<Fact, {
            cluster: string,
            namespace: string,
            workload: string,
            kind: string,
            fact: Fact
        }>({
            query: ({ cluster, namespace, workload, kind, fact }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string,
                fact: Fact
            }) => ({
                url: `/fred/ai/workload/fact?kind=${kind}&cluster_name=${cluster}&namespace=${namespace}&workload_name=${workload}`,
                method: 'PUT',
                body: fact
            }),
        }),
        postClusterFacts: builder.mutation<Fact, {
            cluster: string,
            fact: Fact
        }>({
            query: ({ cluster, fact }: {
                cluster: string,
                fact: Fact
            }) => ({
                url: `/fred/ai/cluster/fact?cluster_name=${cluster}`,
                method: 'PUT',
                body: fact
            }),
        }),
        postNamespaceFacts: builder.mutation<Fact, {
            cluster: string,
            namespace: string,
            fact: Fact
        }>({
            query: ({ cluster, namespace, fact }: {
                cluster: string,
                namespace: string,
                fact: Fact
            }) => ({
                url: `/fred/ai/namespace/fact?cluster_name=${cluster}&namespace=${namespace}`,
                method: 'PUT',
                body: fact
            }),
        }),
        deleteWorkloadFacts: builder.mutation<void, {
            cluster: string,
            namespace: string,
            workload: string,
            kind: string,
            fact: Fact
        }>({
            query: ({ cluster, namespace, workload, fact, kind }: {
                cluster: string,
                namespace: string,
                workload: string,
                kind: string,
                fact: Fact
            }) => ({
                url: `/fred/ai/workload/fact?kind=${kind}&cluster_name=${cluster}&namespace=${namespace}&workload_name=${workload}`,
                method: 'DELETE',
                body: fact
            }),
        }),
        deleteNamespaceFacts: builder.mutation<void, {
            cluster: string,
            namespace: string,
            fact: Fact
        }>({
            query: ({ cluster, namespace, fact }: {
                cluster: string,
                namespace: string,
                fact: Fact
            }) => ({
                url: `/fred/ai/namespace/fact?cluster_name=${cluster}&namespace=${namespace}`,
                method: 'DELETE',
                body: fact
            }),
        }),
        deleteClusterFacts: builder.mutation<void, {
            cluster: string,
            fact: Fact
        }>({
            query: ({ cluster, fact }: {
                cluster: string,
                fact: Fact
            }) => ({
                url: `/fred/ai/cluster/fact?cluster_name=${cluster}`,
                method: 'DELETE',
                body: fact
            }),
        }),
        postTranscribeAudio: builder.mutation<string, { file: File }>({
            query: ({ file }: { file: File }) => {
                const formData = new FormData();
                formData.append("file", file);  // Append the file as part of the form data

                return {
                    url: `/fred/ai/transcribe`,
                    method: 'POST',
                    body: formData,  // Send the FormData object in the body
                    headers: {
                        // 'Content-Type' can be omitted when using FormData, it will be set automatically
                    },
                };
            },
        }),
        postSpeechText: builder.mutation<Blob, string>({
            query: (text) => ({
                url: `/fred/ai/speech`,
                method: 'POST',
                body: text,
                headers: {
                    'Content-Type': 'text/plain',
                },
                responseHandler: (response) => response.blob(),
            }),
        }),
        postFeedback: builder.mutation<{ success: boolean }, {
            rating: number,
            reason: string,
            feedbackType: 'up' | 'down',
            messageId?: string // Optional: you can pass an identifier for the message
        }>({
            query: ({ rating, reason, feedbackType, messageId }) => ({
                url: `/fred/feedback`,
                method: 'POST',
                body: { rating, reason, feedbackType, messageId },
            }),
        }),
    }),
})

export const {
    useGetCarbonConsumptionMutation,
    useGetEnergyConsumptionMutation,
    useGetEnergyMixMutation,
    useGetClusterDescriptionMutation,
    useGetClusterScoresMutation,
    useGetClusterListMutation,
    useGetClustersFootprintsMutation,
    useGetFinopsCostMutation,
    useGetNamespaceListMutation,
    useGetWorkloadListMutation,
    useGetWorkloadEssentialsMutation,
    useGetWorkloadAdvancedMutation,
    useGetWorkloadSummaryMutation,
    useGetClusterSummaryMutation,
    useGetNamespaceSummaryMutation,
    useGetWorkloadIdMutation,
    useGetWorkloadScoreMutation,
    useGetWorkloadFactsMutation,
    usePostWorkloadFactsMutation,
    useDeleteWorkloadFactsMutation,
    useGetNamespaceFactsMutation,
    usePostNamespaceFactsMutation,
    useDeleteNamespaceFactsMutation,
    useGetClusterFactsMutation,
    usePostClusterFactsMutation,
    useDeleteClusterFactsMutation,
    usePostTranscribeAudioMutation,
    usePostSpeechTextMutation,
    useGetTheaterOfOperationMapDataMutation,
} = extendedApi
