#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Module providing a service to manage Kubernetes Clusters.

This module includes the `KubeService` class that implements methods to interact with
Kubernetes Clusters, including listing Clusters, retrieving Namespaces, Deployments,
StatefulSets, and ConfigMaps.
"""

import logging
import re
import traceback
from typing import List, Dict, Any
from os import environ

import urllib3
from kubernetes import client, config
from kubernetes.client import ApiException

from fred.application_context import get_app_context, get_configuration
from fred.services.kube.structure import Cluster, ClusterList, WorkloadKind, WorkloadNameList, Workload, IngressesList, \
    CustomObject, CustomObjectInfo
from fred.services.kube.structure import ConfigMapsList, NamespacesList, Namespace, ServicesList
from fred.common.connectors.file_dao import FileDAO
from fred.common.error import UnavailableError
from fred.common.structure import Configuration, DAOTypeEnum

logger = logging.getLogger(__name__)

class KubeService:
    """
    Access stored resources about Kubernetes clusters.
    """

    def __init__(self):
        """
        Initialize the KubeService.

        Args:
            context (Configuration): The configuration context containing settings for
                DAO connections.
        """
        configuration = get_configuration()
        match configuration.dao.type:
            case DAOTypeEnum.file:
                self.dao = FileDAO(configuration.dao, "kube")
            case dao_type:
                raise NotImplementedError(f"DAO type {dao_type}")

        self.connected_client = ConnectedKubeService()

        logger.info("Initialized Kubernetes service")

    def create_new_custom_object(self, custom_object: CustomObject):
        """
        Create a new file with the description of a custom object.

        Args:
            custom_object (CustomObject): The custom object information to create it.
        """
        custom_object = self.connected_client.create_new_custom_object(custom_object)
        return self.__update_custom_object_description(custom_object)

    def patch_custom_object(self, custom_object: CustomObject) -> CustomObject:
        """
        Patch the given custom object.

        Args:
            custom_object (CustomObject): The custom object information to patch.

        Returns:
            (CustomObject): The patched custom object.
        """
        custom_object = self.connected_client.patch_custom_object(custom_object)
        self.__update_custom_object_description(custom_object)
        return custom_object

    def delete_custom_object(self, custom_object: CustomObject):
        """
        Delete the given custom object.

        Args:
            custom_object (CustomObject): The custom object information to delete.
        """
        self.connected_client.delete_custom_object(custom_object)

        # Delete the cached object
        self.dao.delete(
            CustomObject,
            custom_object.cluster,
            custom_object.namespace,
            custom_object.plural,
            custom_object.name
        )

    def get_clusters_list(self) -> ClusterList:
        """
        Get the list of clusters.
        If the list does not exist and simulation mode is disabled, it will create it by accessing the Kubernetes
        configuration.
        """
        try:
            logger.debug("Reading file for the list of clusters")
            return self.dao.loadCacheItem(ClusterList)
        except FileNotFoundError:
            clusters_list = self.connected_client.get_clusters_list()

            logger.debug("Updating file for the list of clusters")
            self.dao.saveCache(clusters_list)

            return clusters_list

    def get_namespaces_list(self, cluster: str) -> NamespacesList:
        """
        Get the list of Namespaces for a given cluster.
        If the list does not exist and simulation mode is disabled, it will create it by accessing the Kubernetes
        cluster.

        Args:
            cluster (str): The name of the Cluster.

        Returns:
            (NamespacesList): The list of Namespaces.
        """
        try:
            logger.debug(
                "Reading file for the list of Namespaces, cluster=%s", cluster
            )
            return self.dao.loadCacheItem(NamespacesList, cluster)
        except FileNotFoundError:
            namespaces = self.connected_client.get_namespaces_list(cluster)

            logger.debug(
                "Updating file for the list of Namespaces, cluster=%s", namespaces.cluster
            )
            self.dao.saveCache(namespaces, namespaces.cluster)

            return namespaces

    def get_namespace_description(self, cluster: str, namespace: str) -> Namespace:
        """
        Get the description of a Namespace.
        If the resource does not exist and simulation mode is disabled, it will create it by accessing the Kubernetes
        cluster.

        Args:
            cluster (str): The name of the Cluster.
            namespace (str): The name of the Namespace.

        Returns:
            (Namespace): The Namespace description.
        """
        try:
            logger.debug(
                "Reading file for the description of the Namespace, cluster=%s, "
                "namespace=%s",
                cluster,
                namespace,
            )
            return self.dao.loadCacheItem(Namespace, cluster, namespace)
        except FileNotFoundError:
            description = self.connected_client.get_namespace_description(cluster, namespace)

            logger.debug(
                "Updating file for the description of the Namespace, cluster=%s, "
                "namespace=%s",
                description.cluster,
                description.namespace,
            )
            self.dao.saveCache(description, description.cluster, description.namespace)

            return description

    def get_workload_names_list(self, cluster: str, namespace: str, kind: WorkloadKind) -> WorkloadNameList:
        """
        Get the list of workload names.
        If the list does not exist and simulation mode is disabled, it will create it by accessing the Kubernetes
        cluster.

        Args:
            cluster (str): The name of the Cluster.
            namespace (str): The namespace of the workloads.
            kind (WorkloadKind): The kind of the workloads.

        Returns:
            (WorkloadNameList): The list of workloads.
        """
        try:
            logger.debug(
                "Reading file for the list of the workloads, cluster=%s, "
                "namespace=%s",
                cluster,
                namespace,
            )
            return self.dao.loadCacheItem(WorkloadNameList, cluster, namespace, kind)
        except FileNotFoundError:
            workload_names_list = self.connected_client.get_workload_names_list(cluster, namespace, kind)

            logger.debug(
                "Updating file for the list of the workloads, cluster=%s, "
                "namespace=%s, kind=%s",
                workload_names_list.cluster,
                workload_names_list.namespace,
                workload_names_list.kind
            )
            self.dao.saveCache(workload_names_list, workload_names_list.cluster, workload_names_list.namespace,
                          workload_names_list.kind)

            return workload_names_list

    def get_workload_description(self, cluster: str, namespace: str, workload_name: str, kind: WorkloadKind) \
            -> Workload:
        """
        Get the description of a workload.
        If the resource does not exist and simulation mode is disabled, it will create it by accessing the Kubernetes
        cluster.

        Args:
            cluster (str): The name of the Cluster.
            namespace (str): The name of the Namespace.
            workload_name (str): The name of the workload.
            kind (WorkloadKind): The kind of the workload.

        Returns:
            (Workload): The workload description.
        """
        try:
            logger.debug(
                "Reading file for the description of the workload, cluster=%s, "
                "namespace=%s, workload_name=%s",
                cluster,
                namespace,
                workload_name,
            )
            return self.dao.loadCacheItem(Workload, cluster, namespace, kind, workload_name)
        except FileNotFoundError:
            description = self.connected_client.get_workload_description(cluster, namespace, workload_name,
                                                                         kind)

            logger.debug(
                "Updating file for the description of the workload, cluster=%s, "
                "namespace=%s, kind=%s, workload_name=%s",
                cluster,
                namespace,
                kind,
                workload_name
            )
            self.dao.saveCache(
                description,
                cluster,
                namespace,
                kind,
                workload_name
            )

            return description

    def get_custom_object_description(self, custom_object: CustomObject) -> CustomObject:
        """
        Get the description of a custom object.

        Args:
            custom_object (CustomObject): Information about the custom object to get.

        Returns:
            (CustomObject): The custom object description.
        """
        try:
            logger.debug(f"Reading file for the description of the custom object, "
                              f"cluster={custom_object.cluster}, namespace={custom_object.namespace}, "
                              f"custom_object_name={custom_object.name}, group={custom_object.group}, "
                              f"version={custom_object.version}, plural={custom_object.plural}")
            return self.dao.loadCacheItem(
                CustomObject,
                custom_object.cluster,
                custom_object.namespace,
                custom_object.plural,
                custom_object.name
            )
        except FileNotFoundError:
            custom_object_with_body = self.connected_client.get_custom_object_description(custom_object)
            self.__update_custom_object_description(custom_object_with_body)
            return custom_object_with_body

    def get_custom_object_description_list(self, custom_object_info: CustomObjectInfo) -> List[CustomObject]:
        """
        Get the list of custom object descriptions.

        Args:
            custom_object_info (CustomObjectInfo): Information about the custom objects to get.
        """
        try:
            logger.debug(f"Reading file for the description of the custom object list, "
                              f"cluster={custom_object_info.cluster}, namespace={custom_object_info.namespace}, "
                              f"group={custom_object_info.group}, version={custom_object_info.version}, "
                              f"plural={custom_object_info.plural}")
            return self.dao.list(
                CustomObject,
                custom_object_info.cluster,
                custom_object_info.namespace,
                custom_object_info.plural
            )
        except FileNotFoundError:
            return self.connected_client.get_custom_object_description_list(custom_object_info)

    def get_workload_configmaps(self, cluster: str, namespace: str, workload_name: str, kind: WorkloadKind) \
            -> ConfigMapsList:  # pylint: disable=R0913, R0917
        """
        Get the list of ConfigMaps associated with a workload.
        If the list does not exist and simulation mode is disabled, it will create it by accessing the Kubernetes
        cluster.

        Args:
            cluster (str): The name of the Cluster.
            namespace (str): The name of the Namespace.
            workload_name (str): The name of the workload.
            kind (WorkloadKind): The kind of the workload.

        Returns:
            (ConfigMapsList): The list of ConfigMaps.
        """
        try:
            logger.debug(
                "Reading file for the list of ConfigMaps associated with the workload, "
                "cluster=%s, namespace=%s, workload_name=%s",
                cluster,
                namespace,
                workload_name,
            )
            return self.dao.loadCacheItem(
                ConfigMapsList,
                cluster,
                namespace,
                kind,
                workload_name
            )
        except FileNotFoundError:
            config_maps = self.connected_client.get_workload_configmaps(cluster, namespace, workload_name,
                                                                        kind)
            logger.debug(
                "Updating file for the list of ConfigMaps associated with the workload, "
                "cluster=%s, namespace=%s, kind=%, workload_name=%s",
                cluster,
                namespace,
                kind,
                workload_name
            )
            self.dao.saveCache(
                config_maps,
                cluster,
                namespace,
                kind,
                workload_name
            )

            return config_maps

    def get_workload_services(self, cluster: str, namespace: str,
                              workload_name: str, kind: WorkloadKind) -> ServicesList:  # pylint: disable=R0913, R0917
        """
        Get the list of Services associated with a workload.
        If the list does not exist and simulation mode is disabled, it will create it by accessing the Kubernetes
        cluster.

        Args:
            cluster (str): The name of the Cluster.
            namespace (str): The name of the Namespace.
            workload_name (str): The name of the workload.
            kind (WorkloadKind): The kind of the workload.

        Returns:
            (ServicesList): The list of Services.
        """
        try:
            logger.debug(
                "Reading file for the list of Services associated with the workload, "
                "cluster=%s, namespace=%s, workload_name=%s",
                cluster,
                namespace,
                workload_name,
            )
            return self.dao.loadCacheItem(ServicesList, cluster, namespace, kind, workload_name)
        except FileNotFoundError:
            services_list = self.connected_client.get_workload_services(cluster, namespace, workload_name,
                                                                        kind)
            logger.debug(
                "Updating file for the list of Services associated with the workload, "
                "cluster=%s, namespace=%s, kind=%s, workload_name=%s",
                cluster,
                namespace,
                kind,
                workload_name,
            )
            self.dao.saveCache(
                services_list,
                cluster,
                namespace,
                kind,
                workload_name,
            )

            return services_list

    def get_workload_ingresses(self, cluster: str, namespace: str, workload_name: str, kind: WorkloadKind) \
            -> IngressesList:
        """
        Get the list of Ingresses associated with a workload.
        If the list does not exist and simulation mode is disabled, it will create it by accessing the Kubernetes
        cluster.

        Args:
            cluster (str): The name of the Cluster.
            namespace (str): The name of the Namespace.
            workload_name (str): The name of the workload.
            kind (WorkloadKind): The kind of the workload.

        Returns:
            ingresses (IngressesList): The list of Ingresses.

        """
        try:
            logger.debug(
                "Reading file for the list of Ingresses associated with the workload, "
                "cluster=%s, namespace=%s, workload_name=%s",
                cluster,
                namespace,
                workload_name,
            )
            return self.dao.loadCacheItem(IngressesList, cluster, namespace, kind, workload_name)
        except FileNotFoundError:
            ingresses_list = self.connected_client.get_workload_ingresses(cluster, namespace, workload_name,
                                                                          kind)
            logger.debug(
                "Updating file for the list of Ingresses associated with the workload, "
                "cluster=%s, namespace=%s, kind=%s, workload_name=%s",
                cluster,
                namespace,
                kind,
                workload_name,
            )
            self.dao.saveCache(
                ingresses_list,
                cluster,
                namespace,
                kind,
                workload_name,
            )

            return ingresses_list

    def __update_custom_object_description(self, custom_object: CustomObject):
        """
        Update the file with the description of a custom object.

        Args:
            custom_object (CustomObject): The new version of the custom object.
        """
        logger.debug(f"Updating file for the description of the custom object, "
                          f"cluster={custom_object.cluster}, namespace={custom_object.namespace}, "
                          f"custom_object_name={custom_object.name}, group={custom_object.group}, "
                          f"version={custom_object.version}, plural={custom_object.plural}")
        self.dao.saveCache(
            custom_object,
            custom_object.cluster,
            custom_object.namespace,
            custom_object.plural,
            custom_object.name
        )


def requires_online(func):
    """Decorator to check if the service is online before executing a method"""

    def wrapper(self, *args, **kwargs):
        if get_app_context().status.offline:
            raise UnavailableError("The Kubernetes service is currently offline")
        if not self._initialised:
            self._setup_service()
            self._initialised = True
        return func(self, *args, **kwargs)

    return wrapper


class ConnectedKubeService:
    """
    Service class for managing Kubernetes Clusters.

    This class provides methods to interact with Kubernetes Clusters, such as listing
    Clusters, Namespaces, Deployments, and StatefulSets, as well as retrieving detailed
    information about them.
    """

    def __init__(self):
        """
        Initialize the ConnectedKubeService.
        It does not create any client until a method with the offline mode disabled is called.

        Args:
            context (Configuration): The configuration context containing settings for
                Kubernetes connections.
        """
        self.configuration = get_configuration()
        self._initialised = False

    def _setup_service(self):
        """
        Initialize the ConnectedKubeService by creating a client. It requires a valid kubeconfig.
        """
        self.kube_config_path = self.configuration.kubernetes.kube_config
        self.connection_timeout = self.configuration.kubernetes.timeout.connect
        self.read_timeout = self.configuration.kubernetes.timeout.read
        self.api_clients = {}  # Cache ApiClients for each cluster

        config.load_kube_config(self.kube_config_path)  # Global configuration loading for kube clients

        logger.info("Initialized ConnectedKubeService service")

    @requires_online
    def _load_kube_config(self) -> client.ApiClient:
        """
        Load Kubernetes configuration and return an ApiClient with timeouts.

        Returns:
            client.ApiClient: An ApiClient configured with the specified timeouts.
        """
        logger.info(f"Loading Kubernetes configuration '{self.kube_config_path}'")
        try:
            # Create a Kubernetes client configuration with timeouts
            c = client.Configuration.get_default_copy()
            c.timeout_seconds = self.read_timeout  # Set the desired read timeout
            c.read_timeout = self.read_timeout
            c.connect_timeout = self.connection_timeout
            if "HTTP_PROXY" in environ:
                c.proxy = environ["HTTP_PROXY"]
            if "NO_PROXY" in environ:
                c.no_proxy = environ["NO_PROXY"]
            client.Configuration.set_default(c)
            api_client = client.ApiClient(configuration=c)
            api_client.rest_client.pool_manager.connection_pool_kw["timeout"] = (
                urllib3.Timeout(connect=self.connection_timeout, read=self.read_timeout)
            )

            # Return the ApiClient initialized with the configuration
            return api_client

        except Exception as e:
            traceback.print_exc()
            raise e

    @requires_online
    def _get_kube_client(self, cluster: str, api_cls):
        """
        Load the Cluster context and return the configured API client.

        Args:
            cluster (str): The Cluster context to load.
            api_cls: The Kubernetes API class (e.g., CoreV1Api, AppsV1Api).

        Returns:
            Any: An instance of the given API class with a properly configured ApiClient.
        """
        # Load the Cluster context and create a new ApiClient if not cached
        logger.debug(f"Loading Kubernetes Cluster '{cluster}'")
        self.load_cluster_context(cluster)

        # If the ApiClient for this Cluster is cached, return it
        if cluster not in self.api_clients:
            logger.debug(
                f"Client does not exist, creating one for Cluster '{cluster}'"
            )
            api_client = self._load_kube_config()
            self.api_clients[cluster] = api_client
        else:
            logger.debug(
                f"Client for Cluster '{cluster}' already exists, using it"
            )

        # Return the specific Kubernetes API client (e.g., CoreV1Api or AppsV1Api)
        return api_cls(self.api_clients[cluster])

    @requires_online
    def get_clusters_list(self) -> ClusterList:
        """
        Return the list of clusters from the kubeconfig.

        Returns:
            ClusterList: A list of Clusters available in the kubeconfig.
        """
        try:
            self._load_kube_config()
            # Load the context names from kube config
            list_kube_config_contexts, _ = config.list_kube_config_contexts()

            clusters = []
            for kube_config_context in list_kube_config_contexts:
                cluster = kube_config_context["name"]
                try:
                    provider, region, alias = self.parse_cluster(cluster)
                    cluster = Cluster(
                        fullname=cluster,
                        alias=alias,
                        region=region,
                        provider=provider,
                    )
                    clusters.append(cluster)
                    logger.info(f"Loaded Cluster '{cluster}'")
                except Exception as cluster_error:
                    logger.error(
                        f"Error loading Cluster '{cluster}': {cluster_error}"
                    )
                    continue
        except Exception as e:
            traceback.print_exc()
            raise e

        return ClusterList(clusters_list=clusters)

    def parse_cluster(self, cluster: str) -> (str, str, str):
        """
        Parse the Cluster name to extract provider, region, and alias.

        Parses the Cluster name based on known cloud providers to extract the provider,
        region, and alias (short name).

        Args:
            cluster (str): The Cluster name to parse.

        Returns:
            tuple: A tuple containing provider (str), region (str), and alias (str).
        """
        try:
            # AWS (EKS): arn:aws:eks:<region>:<account-id>:cluster/<cluster-name>
            if cluster.startswith("arn:aws:eks"):
                match = re.search(
                    r"eks:([a-z\-0-9]+):[0-9]+:cluster/([a-zA-Z0-9\-]+)",
                    cluster,
                )
                if match:
                    region = match.group(1)  # Extract the region
                    alias = match.group(2)  # Extract the short name (alias)
                    return "AWS", region, alias

            # Google Cloud (GKE): gke_<project-name>_<region>_<cluster-name>
            elif cluster.startswith("gke_"):
                parts = cluster.split("_")
                if len(parts) >= 4:
                    region = parts[2]
                    alias = parts[3]  # The short name of the Cluster
                    return "Google", region, alias

            # Azure (AKS): /subscriptions/<subscription-id>/resourceGroups/<resource-group>/
            # providers/Microsoft.ContainerService/managedClusters/<cluster-name>
            elif (
                    "/subscriptions/" in cluster
                    and "Microsoft.ContainerService" in cluster
            ):
                match = re.search(
                    r"managedClusters/([a-zA-Z0-9\-]+)", cluster
                )
                if match:
                    alias = match.group(1)  # The short name of the Cluster
                    return "Azure", "unknown", alias

            # OVH: ovh_<region>_<cluster-name>
            elif cluster.startswith("ovh_"):
                parts = cluster.split("_")
                if len(parts) >= 3:
                    region = parts[1]
                    alias = parts[2]  # The short name of the Cluster
                    return "OVH", region, alias

            # If no known format matches, return unknown
            return "unknown", "unknown", cluster

        except Exception as e:
            logger.error(f"Error parsing Cluster name '{cluster}': {e}")
            return "unknown", "unknown", cluster

    @requires_online
    def load_cluster_context(self, cluster: str):
        """
        Load the Kubernetes Cluster context for the specified Cluster name.

        Args:
            cluster (str): The name of the Cluster to load the context for.

        Raises:
            ValueError: If the specified Cluster name is not found in kubeconfig.
        """
        # Check if cluster is in the list of Clusters
        if cluster not in {c.fullname for c in
                           self.get_clusters_list().clusters_list}:
            raise ValueError(
                f"Cluster context '{cluster}' not found in kubeconfig file."
            )

        # Load the appropriate Cluster context
        config.load_kube_config(context=cluster)

    @requires_online
    def get_namespaces_list(self, cluster: str) -> NamespacesList:
        """
        Retrieve the list of Namespaces for a given Cluster.

        Args:
            cluster (str): The name of the Cluster.

        Returns:
            NamespacesList: A list of Namespaces within the Cluster.

        Raises:
            Exception: If an error occurs while retrieving Namespaces.
        """
        try:
            logger.info(f"Connecting to Cluster '{cluster}'")
            v1 = self._get_kube_client(cluster, client.CoreV1Api)

            logger.info(f"Connected to Cluster '{cluster}'")
            namespaces = v1.list_namespace()

            logger.info(f"Retrieved Namespaces for Cluster '{cluster}'")
            names = [ns.metadata.name for ns in namespaces.items]

            return NamespacesList(cluster=cluster, namespaces=names)
        except Exception as e:
            logger.error(f"Failed to retrieve Namespaces for Cluster '{e}'")
            raise e  # Propagate errors to be handled by the controller

    @requires_online
    def get_namespace_description(self, cluster: str, namespace: str) -> Namespace:
        """
        Describe a Namespace in detail.

        Args:
            cluster (str): The name of the Cluster.
            namespace (str): The name of the Namespace to describe.

        Returns:
            Namespace: Detailed information about the Namespace.

        Raises:
            Exception: If an error occurs while retrieving Namespace details.
        """
        try:
            v1 = self._get_kube_client(cluster, client.CoreV1Api)
            ns_info = v1.read_namespace(namespace)
            rq_list = v1.list_namespaced_resource_quota(namespace)
            resource_quota = {
                item.metadata.name: item.status.hard for item in rq_list.items
            }
            lr_list = v1.list_namespaced_limit_range(namespace)
            limitrange_resource = {
                item.metadata.name: item.spec.limits for item in lr_list.items
            }

            return Namespace(
                cluster=cluster,
                namespace=namespace,
                labels=ns_info.metadata.labels,
                annotations=ns_info.metadata.annotations,
                status=ns_info.status.phase,
                resource_quota=resource_quota,
                limitrange_quota=limitrange_resource,
            )
        except Exception as e:
            traceback.print_exc()
            raise e  # Propagate errors to be handled by the controller

    @requires_online
    def get_workload_names_list(self, cluster: str, namespace: str, kind: WorkloadKind) -> WorkloadNameList:
        match kind:
            case WorkloadKind.DEPLOYMENT:
                v1 = self._get_kube_client(cluster, client.AppsV1Api)
                workloads = v1.list_namespaced_deployment(namespace)
            case WorkloadKind.STATEFUL_SET:
                v1 = self._get_kube_client(cluster, client.AppsV1Api)
                workloads = v1.list_namespaced_stateful_set(namespace)
            case WorkloadKind.DAEMON_SET:
                v1 = self._get_kube_client(cluster, client.AppsV1Api)
                workloads = v1.list_namespaced_daemon_set(namespace)
            case WorkloadKind.JOB:
                v1 = self._get_kube_client(cluster, client.BatchV1Api)
                workloads = v1.list_namespaced_job(namespace)
            case WorkloadKind.CRONJOB:
                v1 = self._get_kube_client(cluster, client.BatchV1Api)
                workloads = v1.list_namespaced_cron_job(namespace)
            case other:
                raise ValueError(f"Unknown workload kind '{other}'")

        return WorkloadNameList(
            cluster=cluster,
            namespace=namespace,
            workloads=[w.metadata.name for w in workloads.items],
            kind=kind
        )

    @requires_online
    def _get_workload(self, cluster: str, namespace: str, workload_name: str, kind: WorkloadKind):
        match kind:
            case WorkloadKind.DEPLOYMENT:
                v1 = self._get_kube_client(cluster, client.AppsV1Api)
                return v1.read_namespaced_deployment(name=workload_name, namespace=namespace)
            case WorkloadKind.STATEFUL_SET:
                v1 = self._get_kube_client(cluster, client.AppsV1Api)
                return v1.read_namespaced_stateful_set(name=workload_name, namespace=namespace)
            case WorkloadKind.DAEMON_SET:
                v1 = self._get_kube_client(cluster, client.AppsV1Api)
                return v1.read_namespaced_daemon_set(name=workload_name, namespace=namespace)
            case WorkloadKind.JOB:
                v1 = self._get_kube_client(cluster, client.BatchV1Api)
                return v1.read_namespaced_job(name=workload_name, namespace=namespace)
            case WorkloadKind.CRONJOB:
                v1 = self._get_kube_client(cluster, client.BatchV1Api)
                return v1.read_namespaced_cron_job(name=workload_name, namespace=namespace)
            case other:
                raise ValueError(f"Unknown workload kind '{other}'")

    @requires_online
    def get_workload_description(self, cluster: str, namespace: str, workload_name: str,
                                 kind: WorkloadKind) -> Workload:
        workload = self._get_workload(cluster, namespace, workload_name, kind)
        return Workload(cluster=cluster, namespace=namespace, object=workload.to_dict(), kind=kind)

    @requires_online
    def get_custom_object_description(self, custom_object: CustomObject) -> CustomObject:
        custom_object_client = self._get_kube_client(custom_object.cluster, client.CustomObjectsApi)

        custom_object_body = custom_object_client.get_namespaced_custom_object(
            group=custom_object.group,
            version=custom_object.version,
            plural=custom_object.plural,
            namespace=custom_object.namespace,
            name=custom_object.name,
        )

        return custom_object.model_copy(update={"body": custom_object_body}, deep=True)

    @requires_online
    def get_custom_object_description_list(self, custom_object_info: CustomObjectInfo) -> List[CustomObject]:
        custom_object_client = self._get_kube_client(custom_object_info.cluster, client.CustomObjectsApi)

        custom_object_bodies_list = custom_object_client.list_namespaced_custom_object(
            group=custom_object_info.group,
            version=custom_object_info.version,
            plural=custom_object_info.plural,
            namespace=custom_object_info.namespace,
        )

        d = custom_object_info.to_dict()
        return [CustomObject(**d, name=body["metadata"]["name"], body=body) for body in custom_object_bodies_list]

    @requires_online
    def get_workload_configmaps(self, cluster: str, namespace: str, workload_name: str, kind: WorkloadKind) \
            -> ConfigMapsList:
        workload = self._get_workload(cluster, namespace, workload_name, kind)

        volumes = workload.spec.template.spec.volumes
        configmap_objects_list: List[Dict[str, Any]] = self._get_configmaps_from_volumes_spec(cluster, namespace,
                                                                                              volumes)
        return ConfigMapsList(cluster=cluster, namespace=namespace, resource_name=workload_name,
                              config_maps_list=configmap_objects_list, kind=kind)

    @requires_online
    def get_workload_services(self, cluster: str, namespace: str, workload_name: str, kind: WorkloadKind) \
            -> ServicesList:
        workload = self._get_workload(cluster, namespace, workload_name, kind)

        metadata_labels = workload.spec.template.metadata.labels
        service_objects_list: List[Dict[str, Any]] = self.__get_services_from_template_spec(cluster, namespace,
                                                                                            metadata_labels)
        return ServicesList(cluster=cluster, namespace=namespace, resource_name=workload_name,
                            services_list=service_objects_list, kind=kind)

    @requires_online
    def get_workload_ingresses(self, cluster: str, namespace: str, workload_name: str,
                               kind: WorkloadKind) -> IngressesList:
        services_list = self.get_workload_services(cluster, namespace, workload_name, kind).services_list
        services_list_names = {service["metadata"]["name"] for service in services_list}

        if len(services_list) == 0:
            ingresses_list = []
        else:
            networking_v1 = self._get_kube_client(cluster, client.NetworkingV1Api)
            ingresses = networking_v1.list_namespaced_ingress(namespace)

            def has_matching_service(ingress_):
                for rule in ingress_.spec.rules:
                    if rule.http:
                        for path in rule.http.paths:
                            if path.backend.service.name in services_list_names:
                                return True
                return False

            ingresses_list = [ingress.to_dict() for ingress in ingresses.items if has_matching_service(ingress)]

        return IngressesList(cluster=cluster, namespace=namespace, resource_name=workload_name,
                             ingresses_list=ingresses_list, kind=kind)

    @requires_online
    def create_new_custom_object(self, custom_object: CustomObject) -> CustomObject:
        custom_object_client = self._get_kube_client(custom_object.cluster, client.CustomObjectsApi)
        if custom_object.body is None:
            raise ValueError(f"Custom object {custom_object} cannot has an empty body")
        body = custom_object_client.create_namespaced_custom_object(
            group=custom_object.group,
            version=custom_object.version,
            namespace=custom_object.namespace,
            plural=custom_object.plural,
            body=custom_object.body
        )
        return custom_object.model_copy(update={"body": body}, deep=True)

    @requires_online
    def patch_custom_object(self, custom_object: CustomObject) -> CustomObject:
        custom_object_client = self._get_kube_client(custom_object.cluster, client.CustomObjectsApi)
        if custom_object.body is None:
            raise ValueError(f"Custom object {custom_object} cannot has an empty body")
        body = custom_object_client.patch_namespaced_custom_object(
            group=custom_object.group,
            version=custom_object.version,
            namespace=custom_object.namespace,
            plural=custom_object.plural,
            body=custom_object.body
        )
        return custom_object.model_copy(update={"body": body}, deep=True)

    @requires_online
    def delete_custom_object(self, custom_object: CustomObject):
        custom_object_client = self._get_kube_client(custom_object.cluster, client.CustomObjectsApi)
        custom_object_client.delete_namespaced_custom_object(
            group=custom_object.group,
            version=custom_object.version,
            plural=custom_object.plural,
            namespace=custom_object.namespace,
            name=custom_object.name,
        )

    @requires_online
    def _get_configmaps_from_volumes_spec(self, cluster: str, namespace: str, volumes) -> List[Dict[str, Any]]:
        """
        Retrieve ConfigMaps from a Workload's volume specification.

        Args:
            cluster (str): The name of cluster where the workload resides.
            namespace (str): The Namespace of the workload.
            volumes: The list of volume specifications. Can be None.

        Returns:
            List[Dict[str, Any]]: A list of ConfigMaps retrieved from the volumes.

        Raises:
            Exception: If an error occurs while retrieving ConfigMaps.
        """
        if volumes is None:
            return []
        try:
            core_v1 = self._get_kube_client(cluster, client.CoreV1Api)
            configmap_objects_list: List[Dict[str, Any]] = []

            for volume in volumes:
                if volume.config_map:
                    configmap_name = volume.config_map.name
                    try:
                        configmap_object = core_v1.read_namespaced_config_map(
                            name=configmap_name, namespace=namespace
                        )
                    except ApiException as e:
                        if e.status == 404 and volume.config_map.optional:
                            continue
                        else:
                            raise e
                    masked = mask_sensitive_data(configmap_object.to_dict())
                    configmap_objects_list.append(masked)

            return configmap_objects_list
        except Exception as e:
            traceback.print_exc()
            raise e

    @requires_online
    def __get_services_from_template_spec(
            self,
            cluster: str,
            namespace: str,
            metadata_labels: Dict[str, str] | None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve Services from a Workload's metadata labels specification.

        Args:
            cluster (str): The name of cluster where the workload resides.
            namespace (str): The Namespace of the workload.
            metadata_labels (Dict[str, str] | None): The list of labels.

        Returns:
            List[Dict[str, Any]]: A list of Services retrieved from the volumes.

        Raises:
            Exception: If an error occurs while retrieving Services.
        """
        if metadata_labels is None:
            return []
        else:
            set_metadata_labels = set(metadata_labels.items())
        try:
            core_v1 = self._get_kube_client(cluster, client.CoreV1Api)
            list_service_name = core_v1.list_namespaced_service(namespace=namespace)
            service_objects_list: List[Dict[str, Any]] = []

            for service in list_service_name.items:
                service_selector = service.spec.selector

                if service_selector is not None and set(service_selector.items()).issubset(set_metadata_labels):
                    service_name = service.metadata.name

                    service_object = core_v1.read_namespaced_service(name=service_name, namespace=namespace)
                    masked = mask_sensitive_data(service_object.to_dict())

                    service_objects_list.append(masked)

            return service_objects_list
        except Exception as e:
            traceback.print_exc()
            raise e


def mask_sensitive_data(configmap: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mask sensitive data in the ConfigMap.

    Args:
        configmap (Dict[str, Any]): The ConfigMap containing configuration data.

    Returns:
        Dict[str, Any]: The ConfigMap with sensitive data masked.
    """
    sensitive_keywords = [
        "password",
        "secret",
        "token",
        "key",
        "credential",
        "api_key",
        "access_key",
        "private_key",
        "username",
        "client_id",
        "client_secret",
        "database",
        "url",
        "host",
        "port",
        "credentials",
        "ssl",
        "tls",
        "auth",
        "bearer",
        "oauth",
        "bootstrap.servers",
        "security.protocol",
        "sasl.jaas.config",
        "elasticsearch.username",
        "elasticsearch.password",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "opensearch.username",
        "opensearch.password",
        "opensearch.host",
        "opensearch.port",
        "opensearch.cluster.name",
        "opensearch.ssl.verification_mode",
        "opensearch.auth.type",
        "certificate",
        "ssl_certificate",
        "ssl_certificate_key",
        "auth_basic_user_file",
        "auth_basic",
        "proxy_pass",
        "client_max_body_size",
        "server_name",
        "location",
        "rewrite",
        "include",
        "upstream",
        "proxy_set_header",
        "default_type",
        "error_log",
        "access_log",
    ]

    data = configmap.get("data")
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                configmap["data"][key] = redact_sensitive_data(value, sensitive_keywords)
    else:
        logger.debug("Skipping configmap with no or invalid 'data': %s", configmap.get("metadata", {}).get("name"))

    return configmap


def redact_sensitive_data(config_text: str, sensitive_keys: list) -> str:
    """
    Redact sensitive values in the configuration text.

    Args:
        config_text (str): The configuration text to redact.
        sensitive_keys (list): A list of sensitive keys to redact.

    Returns:
        str: The configuration text with sensitive values redacted.
    """
    for key in sensitive_keys:
        # Create a regex pattern to match the key and its value, handling both '=' and ':'
        pattern = rf"({key}\s*[:=]\s*)([^\n]*)"
        # Replace the sensitive value with a placeholder
        config_text = re.sub(
            pattern, r"\1xxx - redacted - xxx", config_text, flags=re.IGNORECASE
        )

    return config_text
