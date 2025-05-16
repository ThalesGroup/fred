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
A controller to expose the (Kubernetes) cluster related endpoints
"""

import logging
import traceback

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from kubernetes.client.exceptions import ApiException

from security.keycloak import KeycloakUser, get_current_user
from services.kube.kube_service import KubeService
from services.kube.structure import Cluster, Workload, WorkloadKind, WorkloadNameList, IngressesList
from services.kube.structure import NamespacesList, Namespace, ConfigMapsList, ServicesList
from common.structure import Configuration
# 🔹 Create a module-level logger
logger = logging.getLogger(__name__)

class KubeController:
    """
    KubeController handles API routes related to Kubernetes Cluster management. It provides endpoints
    to list, describe, and manage Clusters, Namespaces, Deployments, StatefulSets, and ConfigMaps.

    Attributes:
        logger (Logger): A logger instance to log activities.
    """

    def __init__(self, app: APIRouter):
        """
        Initializes KubeController with the provided FastAPI or APIRouter instance and the context.

        Args:
            app (APIRouter): The FastAPI or APIRouter application instance.
            context (Configuration): Configuration object containing Kubernetes and DAO settings.
        """

        # Initialize the Kubernetes service.
        kube_service = KubeService()

        fastapi_tags = ["Kubernetes Cluster APIs"]

        @app.get(
            "/kube/clusters",
            tags=fastapi_tags,
            description="Get the list of Clusters",
            summary="Get the list of Clusters",
        )
        async def get_clusters_list(
            user: KeycloakUser = Depends(get_current_user)
        ) -> list[Cluster]:
            """
            Retrieve the list of Kubernetes Clusters.

            Returns:
                list[Cluster]: A list of Cluster objects.

            Raises:
                HTTPException: If an error occurs during retrieval.
            """
            try:
                return kube_service.get_clusters_list().clusters_list
            except FileNotFoundError as e:
                logger.error(str(e))
                traceback.print_exc()
                raise HTTPException(status_code=404, detail="List of clusters")
            except ApiException as e:
                logger.error(str(e))
                traceback.print_exc()
                raise HTTPException(status_code=e.status, detail=e.reason)
            except Exception as e:
                logger.error(str(e))
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=str(e))

        @app.get(
            "/kube/namespaces",
            tags=fastapi_tags,
            summary="Get the list of Namespaces for the given Cluster.",
        )
        async def get_namespaces_list(cluster_name: str, user: KeycloakUser = Depends(get_current_user)) -> NamespacesList:
            """
            Retrieve the list of Namespaces for a specific Cluster.

            Args:
                cluster_name (str): The name of the Cluster.

            Returns:
                NamespacesList: A list of Namespace objects.

            Raises:
                HTTPException: If an error occurs during retrieval.
            """
            try:
                return kube_service.get_namespaces_list(cluster_name)
            except ApiException as e:
                raise HTTPException(
                    status_code=e.status,
                    detail=(
                        f"Failed to list the Namespaces in Cluster {cluster_name}: "
                        f"{e.reason}"
                    ),
                )
            except FileNotFoundError as e:
                logger.error(f"Resource not found: {e}")
                traceback.print_exc()
                raise HTTPException(
                    status_code=404, detail=f"Resource not found: {e}"
                )
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(
                    status_code=500,
                    detail="An unexpected error occurred: " + str(e),
                )

        @app.get(
            "/kube/namespace",
            tags=fastapi_tags,
            summary=(
                    "Get the description the given Namespace for the specified Cluster. This includes "
                    "labels, annotations, status, resource quota, and limit range."
            ),
        )
        async def get_namespace_description(
                cluster_name: str, namespace: str, user: KeycloakUser = Depends(get_current_user)
        ) -> Namespace:
            """
            Describe a specific Namespace in a Cluster.

            Args:
                cluster_name (str): The name of the Cluster.
                namespace (str): The name of the Namespace.

            Returns:
                Namespace: A Namespace object with detailed information.

            Raises:
                HTTPException: If an error occurs during retrieval.
            """
            try:
                return kube_service.get_namespace_description(
                    cluster=cluster_name, namespace=namespace
                )
            except ApiException as e:
                raise HTTPException(
                    status_code=e.status,
                    detail=(
                        f"Failed to describe the Namespace, Cluster={cluster_name}, "
                        f"Namespace={namespace}: {e.reason}"
                    ),
                )
            except FileNotFoundError as e:
                logger.error(f"Resource not found: {e}")
                traceback.print_exc()
                raise HTTPException(
                    status_code=404, detail=f"Resource not found: {e}"
                )
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(
                    status_code=500,
                    detail="An unexpected error occurred: " + str(e),
                )

        @app.get(
            "/kube/workloads",
            tags=fastapi_tags,
            summary="Get the list of workloads of the given namespace for the specified cluster",
        )
        async def get_workload_names_list(cluster_name: str, namespace: str,
                                          kind: WorkloadKind,
                                          user: KeycloakUser = Depends(get_current_user)
                                          ) -> WorkloadNameList:
            try:
                return kube_service.get_workload_names_list(cluster_name, namespace, kind)
            except ApiException as e:
                raise HTTPException(status_code=e.status,
                                    detail=f"Failed to list workloads, cluster={cluster_name}, "
                                           f"namespace={namespace}, kind={kind}: {e.reason}")
            except FileNotFoundError as e:
                logger.error(str(e))
                traceback.print_exc()
                raise HTTPException(status_code=404, detail="List of workload names")
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail="An unexpected error occurred: " + str(e))

        @app.get(
            "/kube/workload",
            tags=fastapi_tags,
            summary="Get the description of the given workload in the given namespace for the specified cluster",
        )
        async def get_workload_description(cluster_name: str, namespace: str, workload_name: str,
                                           kind: WorkloadKind,
                                           user: KeycloakUser = Depends(get_current_user)
                                           ) -> Workload:
            try:
                return kube_service.get_workload_description(cluster_name, namespace, workload_name, kind)
            except ApiException as e:
                raise HTTPException(status_code=e.status,
                                    detail=f"Failed to describe the workload, cluster={cluster_name}, "
                                           f"namespace={namespace}, workload={workload_name}, kind{kind}: {e.reason}")
            except FileNotFoundError as e:
                logger.error(f"Resource not found: {e}")
                traceback.print_exc()
                raise HTTPException(status_code=404, detail=f"Resource not found: {e}")
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail="An unexpected error occurred: " + str(e))

        @app.get(
            "/kube/configmaps",
            tags=fastapi_tags,
            summary="Get the list of ConfigMaps the given workload in the given namespace for the specified cluster",
        )
        async def get_workload_configmaps(cluster_name: str, namespace: str, workload_name: str,
                                          kind: WorkloadKind,
                                            user: KeycloakUser = Depends(get_current_user)
                                          ) -> ConfigMapsList:
            try:
                return kube_service.get_workload_configmaps(cluster_name, namespace, workload_name, kind)
            except ApiException as e:
                traceback.print_exc()
                raise HTTPException(status_code=e.status,
                                    detail=f"Failed to get the list of ConfigMaps the given workload={workload_name} "
                                           f"of kind={kind} in the given namespace={namespace} "
                                           f"for the specified cluster={cluster_name}: {e.reason}")
            except FileNotFoundError as e:
                logger.error(f"Resource not found: {e}")
                traceback.print_exc()
                raise HTTPException(status_code=404, detail=f"Resource not found: {e}")
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

        @app.get(
            "/kube/services",
            tags=fastapi_tags,
            summary="Get the list of Services the given workload in the given namespace for the specified cluster",
        )
        async def get_workload_services(cluster_name: str, namespace: str, workload_name: str, kind: WorkloadKind,
                                          user: KeycloakUser = Depends(get_current_user)) \
                -> ServicesList:
            try:
                return kube_service.get_workload_services(cluster_name, namespace, workload_name, kind)
            except ApiException as e:
                traceback.print_exc()
                raise HTTPException(status_code=e.status,
                                    detail=f"Failed to get the list of Services the given workload={workload_name} "
                                           f"of kind={kind} in the given namespace={namespace} "
                                           f"for the specified cluster={cluster_name}: {e.reason}")
            except FileNotFoundError as e:
                logger.error(f"Resource not found: {e}")
                traceback.print_exc()
                raise HTTPException(status_code=404, detail=f"Resource not found: {e}")
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

        @app.get(
            "/kube/ingresses",
            tags=fastapi_tags,
            summary="Get the list of Ingresses the given workload in the given namespace for the specified cluster",
        )
        async def get_workload_ingresses(cluster_name: str, namespace: str, workload_name: str, kind: WorkloadKind,
                                          user: KeycloakUser = Depends(get_current_user)) \
                -> IngressesList:
            try:
                return kube_service.get_workload_ingresses(cluster_name, namespace, workload_name, kind)
            except ApiException as e:
                traceback.print_exc()
                raise HTTPException(status_code=e.status,
                                    detail=f"Failed to get the list of Ingresses the given workload={workload_name} "
                                           f"of kind={kind} in the given namespace={namespace} "
                                           f"for the specified cluster={cluster_name}: {e.reason}")
            except FileNotFoundError as e:
                logger.error(f"Resource not found: {e}")
                traceback.print_exc()
                raise HTTPException(status_code=404, detail=f"Resource not found: {e}")
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
