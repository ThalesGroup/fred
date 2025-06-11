# Copyright Thales 2025
#
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

# pylint: disable=C0302
"""
Module that handles the GenAI operations.
"""

import io
import logging
import os
from typing import Dict, Optional

import openai
import yaml
from fastapi import HTTPException, UploadFile, WebSocket
from fastapi.responses import StreamingResponse
from kubernetes import config
from langfuse.callback import CallbackHandler

from application_context import get_app_context, get_configuration
from services.ai.structure.cluster_context import ClusterContext
from services.ai.structure.cluster_summary import ClusterSummary
from services.ai.structure.cluster_topology import ClusterTopology
from services.ai.structure.facts import Fact, Facts
from services.ai.structure.ingress_essentials import IngressesEssentials
from services.ai.structure.namespace_context import NamespaceContext
from services.ai.structure.namespace_summary import NamespaceSummary
from services.ai.structure.namespace_topology import NamespaceTopology
from services.ai.structure.service_essentials import ServicesEssentials
from services.ai.structure.workload_advanced import WorkloadAdvanced
from services.ai.structure.workload_context import WorkloadContext
from services.ai.structure.workload_essentials import WorkloadEssentials
from services.ai.structure.workload_id import WorkloadId
from services.ai.structure.workload_scores import WorkloadScores
from services.ai.structure.workload_summary import WorkloadSummary
from services.ai.structure.workload_topology import WorkloadTopology
from services.kube.kube_service import KubeService
from services.kube.structure import WorkloadKind
from common.connectors.file_dao import FileDAO
from common.error import UnavailableError
from common.structure import Configuration, DAOTypeEnum

# 🔹 Create a module-level logger
logger = logging.getLogger(__name__)

class AIService:  # pylint: disable=R0904
    """
    Service to handle GenAI operations.
    """

    configuration: Configuration
    kube_service: KubeService
    langfuse_handler: Optional[CallbackHandler]

    def __init__(
        self,
        kube_service: KubeService,
        langfuse_handler: Optional[CallbackHandler] = None,
    ):
        """
        Initialize the AI service.

        Args:
            context (Configuration): The configuration object.
            kube_service (KubeService): The Kubernetes service.
            langfuse_handler (Optional[CallbackHandler]): The LangFuse callback handler.
        """
        self.configuration = get_configuration()

        # Bring the storage solution based on configuration.
        match self.configuration.dao.type:
            case DAOTypeEnum.file:
                self.dao = FileDAO(self.configuration.dao, "ai")
            case dao_type:
                raise NotImplementedError(f"DAO type {dao_type}")

        self.kube_service = kube_service
        self.langfuse_handler = langfuse_handler
        config.load_kube_config(self.configuration.kubernetes.kube_config)

    def generate_all_resources(self, cluster_name: str):
        """
        Generate all the GenAI resources for a cluster.

        Args:
            cluster_name (str): The name of the cluster.
        """
        namespaces_list = self.kube_service.get_namespaces_list(cluster_name)

        for namespace in namespaces_list.namespaces:
            for workload_kind in WorkloadKind:
                workload_names = self.kube_service.get_workload_names_list(
                    cluster_name,
                    namespace,
                    workload_kind,
                ).workloads

                for workload in workload_names:
                    self.post_workload_id(
                        cluster_name,
                        namespace,
                        workload,
                        workload_kind,
                    )

                    self.post_workload_essentials(
                        cluster_name,
                        namespace,
                        workload,
                        workload_kind,
                    )

                    self.post_workload_summary(
                        cluster_name,
                        namespace,
                        workload,
                        workload_kind,
                    )

                    self.post_workload_advanced(
                        cluster_name,
                        namespace,
                        workload,
                        workload_kind,
                    )

                    self.post_workload_scores(
                        cluster_name,
                        namespace,
                        workload,
                        workload_kind,
                    )

    def generate_missing_resources(self, cluster_name: str):
        """
        Generate missing GenAI resources for a cluster.

        Args:
            cluster_name (str): The name of the cluster.
        """
        namespaces_list = self.kube_service.get_namespaces_list(cluster_name)

        for namespace in namespaces_list.namespaces:
            for workload_kind in WorkloadKind:
                workload_names = self.kube_service.get_workload_names_list(
                    cluster_name,
                    namespace,
                    workload_kind,
                ).workloads

                for workload in workload_names:
                    try:
                        self.get_workload_id(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )
                        logger.info(
                            "Workload ID for %s '%s' in namespace '%s' already exists",
                            workload_kind.value,
                            workload,
                            namespace,
                        )
                    except Exception:  # pylint: disable=W0718
                        self.post_workload_id(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )

                    try:
                        self.get_workload_essentials(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )
                        logger.info(
                            "Workload Essentials for %s '%s' in namespace '%s' already exists",
                            workload_kind.value,
                            workload,
                            namespace,
                        )
                    except Exception:  # pylint: disable=W0718
                        self.post_workload_essentials(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )

                    try:
                        self.get_workload_summary(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )
                        logger.info(
                            "Workload Summary for %s '%s' in namespace '%s' already exists",
                            workload_kind.value,
                            workload,
                            namespace,
                        )
                    except Exception:  # pylint: disable=W0718
                        self.post_workload_summary(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )

                    try:
                        self.get_workload_advanced(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )
                        logger.info(
                            "Workload Advanced for %s '%s' in namespace '%s' already exists",
                            workload_kind.value,
                            workload,
                            namespace,
                        )
                    except Exception:  # pylint: disable=W0718
                        self.post_workload_advanced(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )

                    try:
                        self.get_workload_scores(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )
                        logger.info(
                            "Workload Scores for %s '%s' in namespace '%s' already exists",
                            workload_kind.value,
                            workload,
                            namespace,
                        )
                    except Exception:  # pylint: disable=W0718
                        self.post_workload_scores(
                            cluster_name,
                            namespace,
                            workload,
                            workload_kind,
                        )

    def _get_cluster_context(
        self,
        cluster_name: str,
    ) -> ClusterContext:
        """
        Get a Cluster Context.

        Args:
            cluster_name (str): The Cluster name.
        """
        namespaces_list = self.kube_service.get_namespaces_list(cluster_name)

        namespace_topologies = []

        for namespace in namespaces_list.namespaces:
            namespace_topology = self.get_namespace_topology(cluster_name, namespace)
            namespace_topologies.append(namespace_topology)

        return ClusterContext(
            name=cluster_name,
            namespace_topologies=namespace_topologies,
        )

    def put_cluster_fact(
        self,
        cluster_name: str,
        fact: Fact,
    ):
        """
        Put a Cluster Fact in storage.

        Args:
            cluster_name (str): The Cluster name.
            fact (Fact): The new Fact.
        """
        cluster_facts = self.get_cluster_facts(cluster_name)
        cluster_facts.facts.append(fact)

        self.dao.save(cluster_facts, cluster_name)
        logger.info(
            "Updated Cluster Facts for Cluster '%s' in storage",
            cluster_name,
        )

    def delete_cluster_fact(
        self,
        cluster_name: str,
        fact: Fact,
    ):
        """
        Delete a Cluster Fact from storage.

        Args:
            cluster_name (str): The Cluster name.
            fact (Fact): The Fact to delete.
        """
        cluster_facts = self.get_cluster_facts(cluster_name)

        try:
            cluster_facts.facts.remove(fact)
            self.dao.save(cluster_facts, cluster_name)
            logger.info(
                "Removed Fact from Cluster '%s' in storage",
                cluster_name,
            )
        except Exception as e:
            logger.error(
                "Failed to remove Fact from Cluster '%s' in storage: %s",
                cluster_name,
                e,
            )
            raise e

    def get_cluster_facts(
        self,
        cluster_name: str,
    ) -> Facts:
        """
        Retrieve the Cluster Facts.

        Args:
            cluster_name (str): The Cluster name.

        Returns:
            Facts: The Cluster Facts.
        """
        try:
            cluster_facts = self.dao.loadItem(Facts, cluster_name)
            logger.debug(
                "Cluster Facts for Cluster '%s' retrieved from storage",
                cluster_name,
            )

            return cluster_facts
        except Exception as e:  # pylint: disable=W0718
            logger.info(
                "Failed to retreive Cluster Facts from storage for Cluster " "'%s': %s",
                cluster_name,
                e,
            )

            return Facts(facts=[])

    def get_cluster_summary(
        self,
        cluster_name: str,
    ) -> ClusterSummary:
        """
        Retrieve the Cluster Summary.

        Args:
            cluster_name (str): The Cluster name.

        Returns:
            ClusterSummary: The Cluster Summary.
        """
        try:
            cluster_summary = self.dao.loadCacheItem(ClusterSummary, cluster_name)
            logger.debug(
                "Cluster Summary for Cluster '%s' retrieved from storage",
                cluster_name,
            )

            return cluster_summary
        except Exception as e:
            logger.info(
                "Failed to retrieve Cluster Summary from storage for Cluster "
                "'%s': %s",
                cluster_name,
                e,
            )
            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e
        self.post_cluster_summary(cluster_name)
        return self.dao.loadCacheItem(ClusterSummary, cluster_name)

    def post_cluster_summary(
        self,
        cluster_name: str,
    ):
        """
        Generate and store the Cluster Summary.

        Args:
            cluster_name (str): The Cluster name.
        """
        cluster_context = self._get_cluster_context(cluster_name)

        logger.info(
            "Trying to generate Cluster Summary for Cluster '%s'",
            cluster_name,
        )
        cluster_summary = ClusterSummary.from_cluster_context(
            cluster_context,
            self.langfuse_handler,
        )

        self.dao.saveCache(cluster_summary, cluster_name)
        logger.info(
            "Generated and stored new Cluster Summary for Cluster '%s'",
            cluster_name,
        )

    def get_cluster_topology(
        self,
        cluster_name: str,
    ) -> ClusterTopology:
        """
        Retrieve the Cluster Topology.

        Args:
            cluster_name (str): The Cluster name.

        Returns:
            ClusterTopology: The Cluster Topology.
        """
        cluster_context = self._get_cluster_context(cluster_name)

        cluster_summary = self.get_cluster_summary(cluster_name)

        cluster_facts = self.get_cluster_facts(cluster_name)

        return ClusterTopology(
            cluster_context=cluster_context,
            cluster_summary=cluster_summary,
            facts=cluster_facts,
        )

    def _get_namespace_context(
        self,
        cluster_name: str,
        namespace: str,
    ) -> NamespaceContext:
        """
        Get a Namespace Context.

        Args:
            cluster_name (str): The Cluster name.
            namespace (str): The Namespace.
        """
        # Retreive the namespace workload topologies.
        workload_topologies = []

        for workload_kind in WorkloadKind:
            workload_names = self.kube_service.get_workload_names_list(
                cluster_name,
                namespace,
                workload_kind,
            ).workloads

            for workload_name in workload_names:
                workload_topology = self.get_workload_topology(
                    cluster_name,
                    namespace,
                    workload_name,
                    workload_kind,
                )
                workload_topologies.append(workload_topology)

        # Retreive the resource quota and limit range resource.
        namespace_description = self.kube_service.get_namespace_description(
            cluster_name,
            namespace,
        )

        if namespace_description.resource_quota is not None:
            resource_quota = yaml.dump(
                namespace_description.resource_quota,
                default_flow_style=False,
                allow_unicode=True,
            )
        else:
            resource_quota = None

        if namespace_description.limitrange_resource is not None:
            limitrange_resource = yaml.dump(
                namespace_description.limitrange_resource,
                default_flow_style=False,
                allow_unicode=True,
            )
        else:
            limitrange_resource = None

        return NamespaceContext(
            name=namespace_description.namespace,
            workload_topologies=workload_topologies,
            resource_quota=resource_quota,
            limitrange_resource=limitrange_resource,
        )

    def put_namespace_fact(
        self,
        cluster_name: str,
        namespace: str,
        fact: Fact,
    ):
        """
        Put a Namespace Fact in storage.

        Args:
            cluster_name (str): The Cluster where the Namespace is running.
            namespace (str): The Namespace.
            fact (Fact): The new Fact.
        """
        namespace_facts = self.get_namespace_facts(cluster_name, namespace)
        namespace_facts.facts.append(fact)

        self.dao.save(namespace_facts, cluster_name, namespace)
        logger.info(
            "Updated Namespace Facts for Namespace '%s' in storage",
            namespace,
        )

    def delete_namespace_fact(
        self,
        cluster_name: str,
        namespace: str,
        fact: Fact,
    ):
        """
        Delete a Namespace Fact from storage.

        Args:
            cluster_name (str): The Cluster where the Namespace is running.
            namespace (str): The Namespace.
            fact (Fact): The Fact to delete.
        """
        namespace_facts = self.get_namespace_facts(cluster_name, namespace)

        try:
            namespace_facts.facts.remove(fact)
            self.dao.save(namespace_facts, cluster_name, namespace)
            logger.info(
                "Removed Fact from Namespace '%s' in storage",
                namespace,
            )
        except Exception as e:
            logger.error(
                "Failed to remove Fact from Namespace '%s' in storage: %s",
                namespace,
                e,
            )
            raise e

    def get_namespace_facts(
        self,
        cluster_name: str,
        namespace: str,
    ) -> Facts:
        """
        Retrieve the Namespace Facts.

        Args:
            cluster_name (str): The Cluster where the Namespace is running.
            namespace (str): The Namespace.

        Returns:
            Facts: The Namespace Facts.
        """
        try:
            namespace_facts = self.dao.loadItem(Facts, cluster_name, namespace)
            logger.debug(
                "Namespace Facts for Namespace '%s' retrieved from storage",
                namespace,
            )

            return namespace_facts
        except Exception as e:  # pylint: disable=W0718
            logger.debug(
                "No saved Facts defined for Namespace "
                "'%s': %s",
                namespace,
                e,
            )

            return Facts(facts=[])

    def get_namespace_summary(
        self,
        cluster_name: str,
        namespace: str,
    ) -> NamespaceSummary:
        """
        Retrieve the Namespace Summary.

        Args:
            cluster_name (str): The Cluster where the Namespace is running.
            namespace (str): The Namespace.

        Returns:
            NamespaceSummary: The Namespace Summary.
        """
        try:
            namespace_summary = self.dao.loadCacheItem(NamespaceSummary, cluster_name, namespace)
            logger.debug(
                "Namespace Summary for Namespace '%s' retrieved from storage",
                namespace,
            )

            return namespace_summary
        except Exception as e:  # pylint: disable=W0718
            logger.info(
                "Failed to retreive Namespace Summary from storage for Namespace "
                "'%s': %s",
                namespace,
                e,
            )
            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e

        self.post_namespace_summary(
            cluster_name,
            namespace,
        )
        return self.dao.loadCacheItem(NamespaceSummary, cluster_name, namespace)

    def post_namespace_summary(
        self,
        cluster_name: str,
        namespace: str,
    ):
        """
        Generate and store the Namespace Summary.

        Args:
            cluster_name (str): The Cluster where the Namespace is running.
            namespace (str): The Namespace.
        """
        namespace_context = self._get_namespace_context(
            cluster_name,
            namespace,
        )

        logger.info(
            "Trying to generate Namespace Summary for Namespace '%s'",
            namespace,
        )
        namespace_summary = NamespaceSummary.from_namespace_context(
            namespace_context,
            self.langfuse_handler,
        )

        self.dao.saveCache(namespace_summary, cluster_name, namespace)
        logger.info(
            "Generated and stored new Namespace Summary for Namespace '%s'",
            namespace,
        )

    def get_namespace_topology(
        self,
        cluster_name: str,
        namespace: str,
    ) -> NamespaceTopology:
        """
        Retrieve the Namespace Topology.

        Args:
            cluster_name (str): The Cluster where the Namespace is running.
            namespace (str): The Namespace.

        Returns:
            NamespaceTopology: The Namespace Topology.
        """
        namespace_context = self._get_namespace_context(
            cluster_name,
            namespace,
        )

        namespace_summary = self.get_namespace_summary(
            cluster_name,
            namespace,
        )

        namespace_facts = self.get_namespace_facts(
            cluster_name,
            namespace,
        )

        return NamespaceTopology(
            namespace_context=namespace_context,
            namespace_summary=namespace_summary,
            facts=namespace_facts,
        )

    def _get_workload_context(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> WorkloadContext:
        """
        Get a Workload Context.

        Args:
            cluster_name (str): The Cluster name.
            namespace (str): The Namespace.
            workload_name (str): The Workload name.
        """
        workload = self.kube_service.get_workload_description(
            cluster_name,
            namespace,
            workload_name,
            workload_kind,
        ).object

        configmaps = self.kube_service.get_workload_configmaps(
            cluster_name, namespace, workload_name, workload_kind
        ).config_maps_list

        services = self.kube_service.get_workload_services(
            cluster_name, namespace, workload_name, workload_kind
        ).services_list

        ingresses = self.kube_service.get_workload_ingresses(
            cluster_name, namespace, workload_name, workload_kind
        ).ingresses_list

        workload_yaml = yaml.dump(
            workload,
            default_flow_style=False,
            allow_unicode=True,
        )

        configmaps_yaml = yaml.dump_all(
            configmaps,
            default_flow_style=False,
            allow_unicode=True,
            explicit_start=True,
        )

        services_yaml = yaml.dump_all(
            services,
            default_flow_style=False,
            allow_unicode=True,
            explicit_start=True,
        )

        ingresses_yaml = yaml.dump_all(
            ingresses,
            default_flow_style=False,
            allow_unicode=True,
            explicit_start=True,
        )

        return WorkloadContext(
            workload_yaml=workload_yaml,
            configmaps_yaml=configmaps_yaml,
            services_yaml=services_yaml,
            ingresses_yaml=ingresses_yaml,
        )

    def get_workload_id(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> WorkloadId:
        """
        Retrieve a Workload Id from storage.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The name of the Workload.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

        Returns:
            WorkloadId: The Deployment Workload ID.
        """
        try:
            workload_id = self.dao.loadCacheItem(
                WorkloadId, cluster_name, namespace, workload_kind, workload_name
            )
            logger.info(
                "Workload Id for Workload '%s' retrieved from storage",
                workload_name,
            )
            return workload_id
        except Exception as e:  # pylint: disable=W0718
            logger.info(
                "Failed to retreive Workload Id from storage for Workload " "'%s': %s",
                workload_name,
                e,
            )
            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e

        self.post_workload_id(cluster_name, namespace, workload_name, workload_kind)
        return self.dao.loadCacheItem(
            WorkloadId, cluster_name, namespace, workload_kind, workload_name
        )

    def post_workload_id(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ):  # pylint: disable=R0913, R0917
        """
        Generate and store a Workload Id.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The name of the Workload.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
        """
        workload_context = self._get_workload_context(
            cluster_name, namespace, workload_name, workload_kind
        )

        logger.info(
            "Trying to generate Workload Id for %s '%s' from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

        workload_id = WorkloadId.from_workload_context(
            workload_context,
            self.langfuse_handler,
        )

        self.dao.saveCache(
            workload_id, cluster_name, namespace, workload_kind, workload_name
        )
        logger.info(
            "Successfully generated and stored new Workload Id for %s '%s' "
            "from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

    def get_workload_essentials(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> WorkloadEssentials:
        """
        Retrieve the Workload Essentials.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

        Returns:
            WorkloadEssentials: The Workload Essentials.
        """
        try:
            workload_essentials = self.dao.loadCacheItem(
                WorkloadEssentials,
                cluster_name,
                namespace,
                workload_kind,
                workload_name,
            )

            logger.debug(
                "Workload Essentials for Workload '%s' retrieved from storage",
                workload_name,
            )

            return workload_essentials
        except Exception as e:  # pylint: disable=W0718
            logger.info(
                "Failed to retreive Workload Essentials from storage for Workload "
                "'%s': %s",
                workload_name,
                e,
            )
            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e

        self.post_workload_essentials(
            cluster_name, namespace, workload_name, workload_kind
        )
        return self.dao.loadCacheItem(
            WorkloadEssentials, cluster_name, namespace, workload_kind, workload_name
        )

    def post_workload_essentials(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ):
        """
        Generate and store the Workload Essentials.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
        """
        workload = self.kube_service.get_workload_description(
            cluster_name,
            namespace,
            workload_name,
            workload_kind,
        ).object

        workload_definition = yaml.dump(
            workload,
            default_flow_style=False,
            allow_unicode=True,
        )

        logger.info(
            "Trying to generate Workload Essentials for %s '%s' from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

        workload_essentials = WorkloadEssentials.from_workload_definition(
            workload_definition,
            self.langfuse_handler,
        )

        self.dao.saveCache(
            workload_essentials, cluster_name, namespace, workload_kind, workload_name
        )
        logger.info(
            "Generated and stored new Workload Essentials for %s '%s' "
            "from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

    def get_workload_summary(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> WorkloadSummary:
        """
        Retrieve the Workload Summary.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

        Returns:
            WorkloadSummary: The Workload Summary.
        """
        try:
            workload_summary = self.dao.loadCacheItem(
                WorkloadSummary, cluster_name, namespace, workload_kind, workload_name
            )
            logger.debug(
                "Workload Summary for Workload '%s' retrieved from storage",
                workload_name,
            )

            return workload_summary
        except Exception as e:  # pylint: disable=W0718
            logger.info(
                "Failed to retreive Workload Summary from storage for Workload "
                "'%s': %s",
                workload_name,
                e,
            )
            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e

        self.post_workload_summary(
            cluster_name, namespace, workload_name, workload_kind
        )
        return self.dao.loadCacheItem(
            WorkloadSummary, cluster_name, namespace, workload_kind, workload_name
        )

    def post_workload_summary(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ):
        """
        Generate and store the Workload Summary.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
        """
        workload_id = self._get_workload_context(
            cluster_name, namespace, workload_name, workload_kind
        )

        logger.info(
            "Trying to generate Workload Summary for %s '%s' from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

        workload_summary = WorkloadSummary.from_workload_context(
            workload_id,
            self.langfuse_handler,
        )

        self.dao.saveCache(
            workload_summary, cluster_name, namespace, workload_kind, workload_name
        )
        logger.info(
            "Generated and stored new Workload Summary for %s '%s' "
            "from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

    def get_workload_advanced(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> WorkloadAdvanced:
        """
        Retrieve the Workload Advanced details.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

        Returns:
            WorkloadAdvanced: The Workload Advanced details.
        """
        try:
            workload_advanced = self.dao.loadCacheItem(
                WorkloadAdvanced, cluster_name, namespace, workload_kind, workload_name
            )
            logger.info(
                "Workload Advanced for Workload '%s' retrieved from storage",
                workload_name,
            )

            return workload_advanced
        except Exception as e:  # pylint: disable=W0718
            logger.info(
                "Failed to retreive Workload Advanced from storage for Workload "
                "'%s': %s",
                workload_name,
                e,
            )
            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e

        self.post_workload_advanced(
            cluster_name, namespace, workload_name, workload_kind
        )
        return self.dao.loadCacheItem(
            WorkloadAdvanced, cluster_name, namespace, workload_kind, workload_name
        )

    def post_workload_advanced(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ):
        """
        Generate and store the Workload Advanced details.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
        """
        workload_id = self.get_workload_id(
            cluster_name, namespace, workload_name, workload_kind
        )

        workload_context = self._get_workload_context(
            cluster_name, namespace, workload_name, workload_kind
        )

        logger.info(
            "Trying to generate Workload Advanced for %s '%s' from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

        workload_advanced = WorkloadAdvanced.from_workload_id_and_context(
            workload_id,
            workload_context,
            self.langfuse_handler,
        )

        self.dao.saveCache(
            workload_advanced, cluster_name, namespace, workload_kind, workload_name
        )
        logger.info(
            "Generated and stored new Workload Advanced for %s '%s' "
            "from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

    def get_workload_scores(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> WorkloadScores:
        """
        Retrieve the Workload Scores.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

        Returns:
            WorkloadScores: The Workload Scores.
        """
        try:
            workload_scores = self.dao.loadCacheItem(
                WorkloadScores, cluster_name, namespace, workload_kind, workload_name
            )
            logger.debug(
                "Workload Scores for Workload '%s' retrieved from storage",
                workload_name,
            )

            return workload_scores
        except Exception as e:  # pylint: disable=W0718
            logger.debug(
                f"Failed to retrieve Workload Scores from storage for Workload '{workload_name}': {e}")

            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e

        self.post_workload_scores(cluster_name, namespace, workload_name, workload_kind)
        return self.dao.loadCacheItem(
            WorkloadScores, cluster_name, namespace, workload_kind, workload_name
        )

    def post_workload_scores(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ):
        """
        Generate and store the Workload Scores.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
        """
        workload_context = self._get_workload_context(
            cluster_name, namespace, workload_name, workload_kind
        )

        logger.info(
            f"Trying to generate Workload Scores for {workload_kind.value} '{workload_name}' from Namespace '{namespace}'"
        )

        workload_scores = WorkloadScores.from_workload_context(
            workload_context,
            self.langfuse_handler,
        )

        self.dao.saveCache(
            workload_scores, cluster_name, namespace, workload_kind, workload_name
        )
        logger.info(
            f"Generated and stored new Workload Scores for {workload_kind.value} '{workload_name}' from Namespace '{namespace}'"
        )

    def get_workload_services_essentials(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> ServicesEssentials:
        """
        Retrieve the Workload Services Essentials.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

        Returns:
            ServicesEssentials: The Workload Services Essentials.
        """
        try:
            services_essentials = self.dao.loadCacheItem(
                ServicesEssentials,
                cluster_name,
                namespace,
                workload_kind,
                workload_name,
            )
            logger.debug(
                "Workload Services Essentials for Workload '%s' retrieved from storage",
                workload_name,
            )

            return services_essentials
        except Exception as e:  # pylint: disable=W0718
            logger.info(
                "Failed to retreive Workload Services Essentials from storage for Workload "
                "'%s': %s",
                workload_name,
                e,
            )
            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e

        self.post_workload_services_essentials(
            cluster_name, namespace, workload_name, workload_kind
        )
        return self.dao.loadCacheItem(
            ServicesEssentials, cluster_name, namespace, workload_kind, workload_name
        )

    def post_workload_services_essentials(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ):
        """
        Generate and store the Workload Services Essentials.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
        """
        services = self.kube_service.get_workload_services(
            cluster_name, namespace, workload_name, workload_kind
        ).services_list

        services_definitions = []
        for service in services:
            service_definition = yaml.dump(
                service,
                default_flow_style=False,
                allow_unicode=True,
            )
            services_definitions.append(service_definition)

        logger.info(
            "Trying to generate Workload Services Essentials for %s '%s' from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )
        services_essentials = ServicesEssentials.from_services_definitions(
            services_definitions,
            self.langfuse_handler,
        )

        self.dao.saveCache(
            services_essentials, cluster_name, namespace, workload_kind, workload_name
        )
        logger.info(
            "Generated and stored new Workload Services Essentials for %s '%s' "
            "from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

    def get_workload_ingresses_essentials(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> IngressesEssentials:
        """
        Retrieve the Workload Ingresses Essentials.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

        Returns:
            IngressesEssentials: The Workload Ingresses Essentials.
        """
        try:
            ingresses_essentials = self.dao.loadCacheItem(
                IngressesEssentials,
                cluster_name,
                namespace,
                workload_kind,
                workload_name,
            )
            logger.debug(
                "Workload Ingresses Essentials for Workload '%s' retrieved from storage",
                workload_name,
            )

            return ingresses_essentials
        except Exception as e:  # pylint: disable=W0718
            logger.info(
                "Failed to retreive Workload Ingresses Essentials from storage for Workload "
                "'%s': %s",
                workload_name,
                e,
            )
            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e

        self.post_workload_ingresses_essentials(
            cluster_name, namespace, workload_name, workload_kind
        )
        return self.dao.loadCacheItem(
            IngressesEssentials, cluster_name, namespace, workload_kind, workload_name
        )

    def post_workload_ingresses_essentials(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ):
        """
        Generate and store the Workload Ingresses Essentials.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
        """
        ingresses = self.kube_service.get_workload_ingresses(
            cluster_name, namespace, workload_name, workload_kind
        ).ingresses_list

        ingresses_definitions = []
        for ingress in ingresses:
            ingress_definition = yaml.dump(
                ingress,
                default_flow_style=False,
                allow_unicode=True,
            )
            ingresses_definitions.append(ingress_definition)

        logger.info(
            "Trying to generate Workload Ingresses Essentials for %s '%s' from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )
        ingresses_essentials = IngressesEssentials.from_ingresses_definitions(
            ingresses_definitions,
            self.langfuse_handler,
        )

        self.dao.saveCache(
            ingresses_essentials, cluster_name, namespace, workload_kind, workload_name
        )
        logger.info(
            "Generated and stored new Workload Ingresses Essentials for %s '%s' "
            "from Namespace '%s'",
            workload_kind.value,
            workload_name,
            namespace,
        )

    def get_workload_topology(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> WorkloadTopology:
        """
        Retrieve the Workload Topology.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

        Returns:
            WorkloadTopology: The Workload Topology.
        """
        workload_id = self.get_workload_id(
            cluster_name, namespace, workload_name, workload_kind
        )
        workload_essential = self.get_workload_essentials(
            cluster_name, namespace, workload_name, workload_kind
        )
        workload_summary = self.get_workload_summary(
            cluster_name, namespace, workload_name, workload_kind
        )
        services_essentials = self.get_workload_services_essentials(
            cluster_name, namespace, workload_name, workload_kind
        )
        ingresses_essentials = self.get_workload_ingresses_essentials(
            cluster_name, namespace, workload_name, workload_kind
        )
        facts = self.get_workload_facts(
            cluster_name, namespace, workload_name, workload_kind
        )

        return WorkloadTopology(
            workload_id=workload_id,
            workload_essentials=workload_essential,
            workload_summary=workload_summary,
            services_essentials=services_essentials,
            ingresses_essentials=ingresses_essentials,
            facts=facts,
        )

    def put_workload_fact(  # pylint: disable=R0913, R0917
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
        fact: Fact,
    ):
        """
        Add a Workload Fact in storage.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
            fact (Fact): The new Workload Fact.
        """
        workload_facts = self.get_workload_facts(
            cluster_name,
            namespace,
            workload_name,
            workload_kind,
        )
        existing_fact_index = next(
            (
                index
                for index, existing_fact in enumerate(workload_facts.facts)
                if existing_fact.title == fact.title
            ),
            None,
        )

        if existing_fact_index is not None:
            # Replace the existing fact
            workload_facts.facts[existing_fact_index] = fact
            logger.debug(
                "Replaced existing Fact with title '%s' for Workload '%s' in Namespace '%s'",
                fact.title,
                workload_name,
                namespace,
            )
        else:
            # Append the new fact
            workload_facts.facts.append(fact)
            logger.debug(
                "Added new Fact with title '%s' for Workload '%s' in Namespace '%s'",
                fact.title,
                workload_name,
                namespace,
            )

        self.dao.saveCache(
            workload_facts, cluster_name, namespace, workload_kind, workload_name
        )
        logger.info(
            "Updated Workload Facts for Namespace '%s' in storage",
            namespace,
        )

    def delete_workload_fact(  # pylint: disable=R0913, R0917
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
        fact: Fact,
    ):
        """
        Remove a Workload Fact from storage.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_name (str): The Workload name.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
            fact (Fact): The Fact to remove.
        """
        workload_facts = self.get_workload_facts(
            cluster_name,
            namespace,
            workload_name,
            workload_kind,
        )

        try:
            workload_facts.facts.remove(fact)
            self.dao.saveCache(
                workload_facts, cluster_name, namespace, workload_kind, workload_name
            )
            logger.info(
                "Removed Fact from Namespace '%s' in storage",
                namespace,
            )
        except Exception as e:  # pylint: disable=W0718
            logger.error(
                "Failed to remove Fact from Namespace '%s' in storage: %s",
                namespace,
                e,
            )
            raise e

    def get_workload_facts(
        self,
        cluster_name: str,
        namespace: str,
        workload_name: str,
        workload_kind: WorkloadKind,
    ) -> Facts:
        """
        Retrieve the Workload Facts.

        Args:
            cluster_name (str): The Cluster where the Workload is running.
            namespace (str): The Namespace where the Workload is running.
            workload_kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
            workload_name (str): The Workload name.

        Returns:
            Facts: The Workload Facts.
        """
        try:
            workload_facts = self.dao.loadCacheItem(
                Facts, cluster_name, namespace, workload_kind, workload_name
            )
            logger.debug(
                "Workload Facts for Workload '%s' retrieved from storage",
                workload_name,
            )

            return workload_facts
        except Exception as e:  # pylint: disable=W0718
            logger.info(
                "Workload Facts for Workload '%s' not found in storage: %s",
                workload_name,
                e,
            )
            return Facts(facts=[])

    async def get_transcribe(self, file: UploadFile) -> Dict[str, str]:
        """
        Get the transcription of an audio file.

        Args:
            file (UploadFile): The audio file to transcribe.

        Returns:
            str: The transcription of the audio file.
        """
        try:
            openai.api_key = os.getenv("OPENAI_API_KEY")
        except Exception as e:
            logger.error(
                "OpenAI API key not found for transcribe generation: %s", e
            )

            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e
            else:
                raise HTTPException(
                    status_code=500, detail="Internal server error."
                ) from e

        try:
            audio_bytes = await file.read()
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = file.filename

            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",
            )

            return {"text": transcript.text}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def get_speech(self, text: str) -> StreamingResponse:
        """
        Get the speech of a text.

        Args:
            text (str): The text to convert to speech.

        Returns:
            StreamingResponse: The speech of the text as an audio stream.
        """
        try:
            # Load the OpenAI API key
            openai.api_key = os.getenv("OPENAI_API_KEY")
        except Exception as e:  # pylint: disable=W0718
            logger.error("OpenAI API key not found for speech generation: %s", e)
            if get_app_context().status.offline:
                raise UnavailableError("AI client") from e
            else:
                raise HTTPException(
                    status_code=500, detail="Internal server error."
                ) from e
        try:
            response = openai.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text,
            )

            audio_bytes_io = io.BytesIO()

            for chunk in response.iter_bytes():
                audio_bytes_io.write(chunk)

            audio_bytes_io.seek(0)

            return StreamingResponse(
                audio_bytes_io,
                media_type="audio/mpeg",
                headers={"Content-Disposition": "attachment; filename=output.mp3"},
            )

        except Exception as e:
            logger.error(
                "An unexpected error occurred while generating the speech: %s", e
            )
            raise HTTPException(status_code=500, detail=str(e)) from e
