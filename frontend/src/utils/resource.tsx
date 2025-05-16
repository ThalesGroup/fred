export interface WorkloadNameList {
    cluster: string,
    namespace: string,
    kind: string,
    workloads: string[]
}

export interface Workload {
    kind: string,
    name: string,
    namespace: string;
}
