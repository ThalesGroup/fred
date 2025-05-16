from enum import Enum
from typing import Dict, Callable, List
from uuid import uuid4

import yaml
from langchain_core.tools import tool

from services.kube.kube_service import KubeService
from common.structure import WorkloadKind


class TargetKind(Enum):
    DEPLOYMENT: str = "Deployment"
    STATEFUL_SET: str = "StatefulSet"


def generate_unique_name() -> str:
    """
    Generate a unique name.

    :return: A unique string.
    """
    return str(uuid4())


@tool
def generate_keda_cron_configuration(
        namespace: str,
        target_name: str,
        target_kind: str,
        timezone: str,
        start_cron: str,
        end_cron: str,
        desired_replicas: int,
) -> Dict[str, Dict | str]:
    """
    Generate a **valid KEDA ScaledObject** JSON configuration for cron-based scaling.

    :param namespace: The namespace for the configuration, usually the same of the target.
    :param target_name: The name of the target to scale.
    :param target_kind: The kind of the target (e.g., Deployment, StatefulSet).
    :param timezone: The time zone of the target.
    The acceptable values would be a value from the IANA Time Zone Database.
    :param start_cron: The cron schedule for when scaling should start.
    The format is the “Linux format cron” (Minute Hour Dom Month Dow).
    :param end_cron: The cron schedule for when scaling should end.
    The format is the “Linux format cron” (Minute Hour Dom Month Dow).
    :param desired_replicas: The desired number of replicas.

    :return: A **JSON dictionary** representing the **KEDA ScaledObject**.
    """
    metadata = {
        "name": generate_unique_name(),
        "namespace": namespace
    }

    return {
        "apiVersion": "keda.sh/v1alpha1",
        "kind": "ScaledObject",
        "metadata": metadata,
        "spec": {
            "scaleTargetRef": {
                "name": target_name,
                "kind": target_kind
            },
            "triggers": [
                {
                    'type': 'cron',
                    'metadata': {
                        'timezone': timezone,
                        'start': start_cron,
                        'end': end_cron,
                        'desiredReplicas': str(desired_replicas)
                    }
                }
            ]
        }
    }


@tool
def generate_keda_prometheus_configuration(
        namespace: str,
        target_name: str,
        target_kind: TargetKind,
        prometheus_url: str,
        metric: str,
        query: str,
        min_replicas: int,
        max_replicas: int,
        threshold: int
) -> Dict[str, Dict | str | int]:
    """
    Generate a **valid KEDA ScaledObject** JSON configuration for Prometheus metrics-based scaling.

    :param namespace: The namespace where the target is located in the Kubernetes cluster.
    :param target_name: The name of the target resource to scale.
    :param target_kind: The kind of the target resource to scale (e.g., Deployment, StatefulSet).
    :param prometheus_url: The URL of the Prometheus metrics service.
    :param metric: The name of the metric to be used for scaling (e.g., `http_requests_total`).
    :param query: The Prometheus query string used to fetch the metric data (e.g., `sum(rate(http_requests_total[5m]))`).
    :param min_replicas: The minimum number of replicas for the target resource when scaling down.
    :param max_replicas: The maximum number of replicas for the target resource when scaling up.
    :param threshold: The threshold value of the metric, above which scaling up will occur.

    :return: A **JSON dictionary** representing the **KEDA ScaledObject**.
    """
    metadata = {
        "name": generate_unique_name(),
        "namespace": namespace
    }

    # Define the KEDA ScaledObject configuration
    return {
        "apiVersion": "keda.sh/v1alpha1",
        "kind": "ScaledObject",
        "metadata": metadata,
        "spec": {
            "scaleTargetRef": {
                "name": target_name,
                "kind": target_kind.value  # The kind of the target resource (e.g., 'Deployment')
            },
            "minReplicaCount": min_replicas,
            "maxReplicaCount": max_replicas,
            "triggers": [
                {
                    'type': 'prometheus',  # The scaling trigger type (Prometheus)
                    'metadata': {
                        'serverAddress': prometheus_url,  # Prometheus server URL
                        'metricName': metric,  # The name of the metric to track
                        'threshold': str(threshold),  # Threshold for scaling
                        'query': query  # The Prometheus query for the metric
                    }
                }
            ]
        }
    }


def get_prometheus_url_tool(kube_service: KubeService) -> Callable[[str], str]:
    """
    Creates a tool function to fetch the internal Prometheus URL for a given cluster.

    :param kube_service: An instance of a KubeService class that provides methods to interact with the cluster,
                         such as listing namespaces, workloads, and services.
    :return: A callable tool function that takes a cluster name as input and returns the
             internal Prometheus URL as a string. The URL follows the format
             'http://<service>.<namespace>.svc.cluster.local:<port>'.
    """

    @tool
    def get_prometheus_url(cluster: str) -> str:
        """
        Get the internal Prometheus URL for a given cluster.

        This function searches for a Prometheus service within the cluster, retrieves its
        details, and constructs an internal URL that is reachable from within the cluster.

        :param cluster: The cluster name.
        :return: The internal Prometheus URL as a string in the format
                 'http://<service>.<namespace>.svc.cluster.local:<port>'.

        :raises ValueError: If no Prometheus service is found in the cluster.
        """
        namespaces = kube_service.get_namespaces_list(cluster).namespaces
        for namespace in namespaces:
            for kind in [WorkloadKind.DEPLOYMENT, WorkloadKind.STATEFUL_SET]:
                # Prometheus can be a Deployment or a StatefulSet
                workload_names = kube_service.get_workload_names_list(cluster, namespace, kind).workloads
                for workload_name in workload_names:
                    services = kube_service.get_workload_services(cluster, namespace, workload_name, kind).services_list
                    for service_description in services:
                        # Step 2: Check for a service named 'prometheus' or containing Prometheus in labels
                        service_name = service_description['metadata']['name']
                        if 'prometheus' in service_name.lower() or 'prometheus' in service_description.get('metadata',
                                                                                                           {}).get(
                            'labels', {}):
                            # Step 3: Construct the internal URL
                            service_port = service_description['spec']['ports'][0]['port']
                            prometheus_url = f"http://{service_name}.{namespace}.svc.cluster.local:{service_port}"
                            return prometheus_url

        raise ValueError("Prometheus service not found in the cluster.")

    return get_prometheus_url


def get_workload_tool(kube_service: KubeService) -> Callable[[str, str, str, WorkloadKind], str]:
    """
    Creates a tool function that retrieves and formats the YAML description of a specified workload
    in a Kubernetes cluster.

    :param kube_service: An instance of the KubeService class, used to interact with the cluster
                         and retrieve workload details.
    :return: A callable function that takes cluster details and returns a YAML-formatted workload description.
    """

    @tool
    def get_workload(cluster: str, namespace: str, name: str, kind: WorkloadKind) -> str:
        """
        Retrieves the description of a workload in a given Kubernetes cluster and returns it
        as a YAML-formatted string.

        :param cluster: The name of the Kubernetes cluster.
        :param namespace: The namespace in which the workload is located.
        :param name: The name of the workload.
        :param kind: The kind of the workload (e.g., Deployment, StatefulSet, DaemonSet).
        :return: A string containing the YAML-formatted description of the workload.
        :raises Exception: If the workload description cannot be retrieved or formatted.
        """
        object_dict = kube_service.get_workload_description(cluster, namespace, name, kind).object
        return yaml.dump(object_dict, default_flow_style=False)

    return get_workload


def get_workload_name_list_tool(kube_service: KubeService) -> Callable[[str, str, WorkloadKind], str]:
    """
    Creates a tool function that retrieves a list of workload names in a specified Kubernetes cluster
    and formats them as a custom list string.

    :param kube_service: An instance of the KubeService class, used to interact with the cluster
                         and retrieve workload details.
    :return: A callable function that takes cluster details and returns a custom-formatted string
             containing the list of workload names.
    """

    @tool
    def get_workload_name_list(cluster: str, namespace: str, kind: WorkloadKind) -> str:
        """
        Retrieves the list of workload names in a given Kubernetes cluster, namespace, and kind and formats them
        into a custom string, where each name is prefixed with "- ".

        :param cluster: The name of the Kubernetes cluster.
        :param namespace: The namespace in which the workloads are located.
        :param kind: The kind of the workload (e.g., Deployment, StatefulSet, DaemonSet).
        :return: A string formatted as a list with each workload name prefixed by "- ".
        :raises Exception: If the list of workload names cannot be retrieved.
        """
        list_names: List[str] = kube_service.get_workload_names_list(cluster, namespace, kind).workloads
        formatted: str = "\n".join(f"- {item}" for item in list_names)
        return formatted

    return get_workload_name_list


# TODO
def get_facts_tool(kube_service: KubeService):
    @tool
    def get_facts():
        ...

    return get_facts
