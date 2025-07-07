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
Module for the AI Controller.
"""

import logging
from fastapi import (APIRouter, Body, Depends, FastAPI, File, HTTPException, Query,
                     UploadFile)

from fred.common.utils import log_exception
from fred.security.keycloak import KeycloakUser, get_current_user
from fred.services.ai.ai_service import AIService
from fred.services.ai.structure.cluster_summary import ClusterSummary
from fred.services.ai.structure.cluster_topology import ClusterTopology
from fred.services.ai.structure.facts import Fact, Facts
from fred.services.ai.structure.namespace_summary import NamespaceSummary
from fred.services.ai.structure.namespace_topology import NamespaceTopology
from fred.services.ai.structure.workload_advanced import WorkloadAdvanced
from fred.services.ai.structure.workload_essentials import WorkloadEssentials
from fred.services.ai.structure.workload_id import WorkloadId
from fred.services.ai.structure.workload_scores import WorkloadScores
from fred.services.ai.structure.workload_summary import WorkloadSummary
from fred.services.ai.structure.workload_topology import WorkloadTopology
from fred.services.kube.kube_service import KubeService
from fred.services.kube.structure import WorkloadKind
from fred.common.structure import Configuration

# 🔹 Create a module-level logger
logger = logging.getLogger(__name__)

class AIController:  # pylint: disable=R0914, R0915, R0903
    """
    A Controller for the AI Service.
    """

    def __init__(self, app: FastAPI | APIRouter, ai_service: AIService):
        """
        Initialize the AI Controller.

        Args:
            app (FastAPI | APIRouter): The FastAPI app or APIRouter.
            context (Configuration): The configuration object.
        """
        fastapi_tags = ["AI Service APIs"]

        @app.post(
            "/ai/transcribe",
            tags=fastapi_tags,
            summary="Get the transcribe of an audio file",
        )
        async def get_transcribe(file: UploadFile = File(...)):
            try:
                return await ai_service.get_transcribe(file)
            except HTTPException as e:
                logger.error(
                    (
                        f"An unexpected error occurred while transcribing the audio file: {e}"
                    )
                )

                raise e
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while transcribing the audio file: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail="An error occurred while transcribing the audio file",
                ) from e

        @app.post(
            "/ai/speech",
            tags=fastapi_tags,
            summary="Get the speech of a text",
        )
        async def get_speech(text: str = Body(...)):
            try:
                return await ai_service.get_speech(text)
            except HTTPException as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating the speech: {e}"
                    )
                )

                raise e
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating the speech: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail="An error occurred while generating the speech",
                ) from e

        @app.post(
            "/ai/cluster/all",
            tags=fastapi_tags,
            summary="Generate all the resources for the cluster",
        )
        async def generate_all_resources(cluster_name: str = Query(..., description="The Cluster name")):
            """
            Generate all the resources for the cluster.

            Args:
                cluster_name (str): The Cluster name.
            """
            try:
                ai_service.generate_all_resources(cluster_name)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating all resources for "
                        f"Cluster {cluster_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while generating all resources for Cluster "
                        f"{cluster_name}"
                    ),
                ) from e

        @app.post(
            "/ai/cluster/missing",
            tags=fastapi_tags,
            summary="Generate all the missing resources for the cluster",
        )
        async def generate_missing_resources(cluster_name: str = Query(..., description="The Cluster name")):
            """
            Generate the missing resources for the cluster.

            Args:
                cluster_name (str): The Cluster name.
            """
            try:
                ai_service.generate_missing_resources(cluster_name)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating missing resources for "
                        f"Cluster {cluster_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while generating missing resources for Cluster "
                        f"{cluster_name}"
                    ),
                ) from e

        @app.put(
            "/ai/cluster/fact",
            tags=fastapi_tags,
            summary="Add a Fact to the Cluster",
        )
        async def put_cluster_fact(
                cluster_name: str = Query(..., description="The Cluster name"),
                fact: Fact = Body(...),
        ):
            """
            Add a Fact to the Cluster.

            Args:
                cluster_name (str): The Cluster name.
                fact (Fact): The Fact to add.
            """
            try:
                ai_service.put_cluster_fact(cluster_name, fact)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while adding a Fact to Cluster "
                        f"{cluster_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while adding a Fact to Cluster {cluster_name}"
                    ),
                ) from e

        @app.delete(
            "/ai/cluster/fact",
            tags=fastapi_tags,
            summary="Delete a Fact from the Cluster",
        )
        async def delete_cluster_fact(
                cluster_name: str = Query(..., description="The Cluster name"),
                fact: Fact = Body(...),
        ):
            """
            Delete a Fact from the Cluster.

            Args:
                cluster_name (str): The Cluster name.
                fact (Fact): The Fact to delete.
            """
            try:
                ai_service.delete_cluster_fact(cluster_name, fact)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while deleting a Fact from Cluster "
                        f"{cluster_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while deleting a Fact from Cluster {cluster_name}"
                    ),
                ) from e

        @app.get(
            "/ai/cluster/facts",
            tags=fastapi_tags,
            summary="Get the Cluster Facts",
        )
        async def get_cluster_facts(
                cluster_name: str = Query(..., description="The Cluster name"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> Facts:
            """
            Get the Cluster Facts.

            Args:
                cluster_name (str): The Cluster name.

            Returns:
                Facts: The Cluster Facts.
            """
            try:
                return ai_service.get_cluster_facts(cluster_name)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Cluster Facts for "
                        f"Cluster {cluster_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Cluster Facts for Cluster "
                        f"{cluster_name}"
                    ),
                ) from e

        @app.get(
            "/ai/cluster/summary",
            tags=fastapi_tags,
            summary="Get the Cluster Summary",
        )
        async def get_cluster_summary(cluster_name: str = Query(..., description="The Cluster name"),
                                      user: KeycloakUser = Depends(get_current_user)
                                      ) \
                -> ClusterSummary:
            """
            Get the Cluster Summary.

            Args:
                cluster_name (str): The Cluster name.

            Returns:
                str: The Cluster Summary.
            """
            try:
                return ai_service.get_cluster_summary(cluster_name)
            except Exception as e:
                log_exception(e,
                        f"An unexpected error occurred while retrieving the Cluster Summary for "
                        f"Cluster {cluster_name}: {e}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Cluster Summary for Cluster "
                        f"{cluster_name}"
                    ),
                ) from e

        @app.post(
            "/ai/cluster/summary",
            tags=fastapi_tags,
            summary="Generate the Cluster Summary",
        )
        async def post_cluster_summary(
                cluster_name: str = Query(..., description="The Cluster name"),
        ):
            """
            Generate the Cluster Summary.

            Args:
                cluster_name (str): The Cluster name.
            """
            try:
                ai_service.post_cluster_summary(cluster_name)
            except Exception as e:
                log_exception(e,
                        f"An unexpected error occurred while generating the Cluster Summary for "
                        f"Cluster {cluster_name}: {e}"
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while generating the Cluster Summary for Cluster "
                        f"{cluster_name}"
                    ),
                ) from e

        @app.get(
            "/ai/cluster/topology",
            tags=fastapi_tags,
            summary="Get the Cluster Topology",
        )
        async def get_cluster_topology(
                cluster_name: str = Query(..., description="The Cluster name"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> ClusterTopology:
            """
            Get the Cluster Topology.

            Args:
                cluster_name (str): The Cluster name.

            Returns:
                str: The Cluster Topology.
            """
            try:
                return ai_service.get_cluster_topology(cluster_name)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Cluster Topology for "
                        f"Cluster {cluster_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Cluster Topology for Cluster "
                        f"{cluster_name}"
                    ),
                ) from e

        @app.put(
            "/ai/namespace/fact",
            tags=fastapi_tags,
            summary="Add a Fact to the Namespace",
        )
        async def put_namespace_fact(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                fact: Fact = Body(...),
        ):
            """
            Add a Fact to the Namespace.

            Args:
                cluster_name (str): The Cluster where the Namespace is running.
                namespace (str): The Namespace.
                fact (Fact): The Fact to add.
            """
            try:
                ai_service.put_namespace_fact(cluster_name, namespace, fact)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while adding a Fact to Namespace "
                        f"{namespace}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while adding a Fact to Namespace {namespace}"
                    ),
                ) from e

        @app.delete(
            "/ai/namespace/fact",
            tags=fastapi_tags,
            summary="Delete a Fact from the Namespace",
        )
        async def delete_namespace_fact(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                fact: Fact = Body(...),
        ):
            """
            Delete a Fact from the Namespace.

            Args:
                cluster_name (str): The Cluster where the Namespace is running.
                namespace (str): The Namespace.
                fact (Fact): The Fact to delete.
            """
            try:
                ai_service.delete_namespace_fact(cluster_name, namespace, fact)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while deleting a Fact from Namespace "
                        f"{namespace}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while deleting a Fact from Namespace {namespace}"
                    ),
                ) from e

        @app.get(
            "/ai/namespace/facts",
            tags=fastapi_tags,
            summary="Get the Namespace Facts",
        )
        async def get_namespace_facts(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> Facts:
            """
            Get the Namespace Facts.

            Args:
                cluster_name (str): The Cluster where the Namespace is running.
                namespace (str): The Namespace.

            Returns:
                Facts: The Namespace Facts.
            """
            try:
                return ai_service.get_namespace_facts(cluster_name, namespace)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Namespace Facts for "
                        f"Namespace {namespace}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Namespace Facts for "
                        f"Namespace {namespace}"
                    ),
                ) from e

        @app.get(
            "/ai/namespace/summary",
            tags=fastapi_tags,
            summary="Get the Namespace Summary",
        )
        async def get_namespace_summary(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> NamespaceSummary:
            """
            Get the Namespace Summary.

            Args:
                cluster_name (str): The Cluster where the Namespace is running.
                namespace (str): The Namespace.

            Returns:
                NamespaceSummary: The Namespace Summary.
            """
            try:
                return ai_service.get_namespace_summary(cluster_name, namespace)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Namespace Summary for "
                        f"Namespace {namespace}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Namespace Summary for "
                        f"Namespace {namespace}"
                    ),
                ) from e

        @app.post(
            "/ai/namespace/summary",
            tags=fastapi_tags,
            summary="Generate the Namespace Summary",
        )
        async def post_namespace_summary(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
        ):
            """
            Generate the Namespace Summary.

            Args:
                cluster_name (str): The Cluster where the Namespace is running.
                namespace (str): The Namespace.
            """
            try:
                ai_service.post_namespace_summary(cluster_name, namespace)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating the Namespace Summary for "
                        f"Namespace {namespace}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while generating the Namespace Summary for "
                        f"Namespace {namespace}"
                    ),
                ) from e

        @app.get(
            "/ai/namespace/topology",
            tags=fastapi_tags,
            summary="Get the Namespace Topology",
        )
        async def get_namespace_topology(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> NamespaceTopology:
            """
            Get the Namespace Topology.

            Args:
                cluster_name (str): The Cluster where the Namespace is running.
                namespace (str): The Namespace.

            Returns:
                NamespaceTopology: The Namespace Topology.
            """
            try:
                return ai_service.get_namespace_topology(cluster_name, namespace)
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Namespace Topology for "
                        f"Namespace {namespace}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Namespace Topology for "
                        f"Namespace {namespace}"
                    ),
                ) from e

        @app.get(
            "/ai/workload/id",
            tags=fastapi_tags,
            summary="Get the Workload ID (Commercial Off-The-Shelf software name)",
        )
        async def get_workload_id(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> WorkloadId:
            """
            Get the Workload id (Commercial Off-The-Shelf software name).

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The name of the Workload.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

            Returns:
                WorkloadId: The Workload ID.
            """
            try:
                return ai_service.get_workload_id(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Workload ID for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Workload ID for Workload "
                        f"{workload_name}: {e}"
                    ),
                ) from e

        @app.post(
            "/ai/workload/id",
            tags=fastapi_tags,
            summary="Generate the Workload ID (Commercial Off-The-Shelf software name)",
        )
        async def post_workload_id(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
        ):
            """
            Generate Workload ID (Commercial Off-The-Shelf software name).

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The name of the Workload.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
            """
            try:
                ai_service.post_workload_id(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating the Workload ID for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while generating the Workload ID for Workload "
                        f"{workload_name}: {e}"
                    ),
                ) from e

        @app.get(
            "/ai/workload/essentials",
            tags=fastapi_tags,
            summary="Get the Workload Essentials",
        )
        async def get_workload_essentials(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> WorkloadEssentials:
            """
            Get the Workload Essentials.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

            Returns:
                WorkloadEssentials: The Workload Essentials.
            """
            try:
                return ai_service.get_workload_essentials(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Workload Essentials "
                        f"for Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Workload Essentials for "
                        f"Workload {workload_name}"
                    ),
                ) from e

        @app.post(
            "/ai/workload/essentials",
            tags=fastapi_tags,
            summary="Generate the Workload Essentials",
        )
        async def post_workload_essentials(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
        ):
            """
            Generate Workload Essentials.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
            """
            try:
                ai_service.post_workload_essentials(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating the Workload Essentials "
                        f"for Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while generating the Workload Essentials for "
                        f"Workload {workload_name}"
                    ),
                ) from e

        @app.get(
            "/ai/workload/summary",
            tags=fastapi_tags,
            summary="Get the Workload Summary",
        )
        async def get_workload_summary(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> WorkloadSummary:
            """
            Get the Workload Summary.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

            Returns:
                WorkloadSummary: The Workload Summary.
            """
            try:
                return ai_service.get_workload_summary(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Workload Summary for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Workload Summary for "
                        f"Workload {workload_name}"
                    ),
                ) from e

        @app.post(
            "/ai/workload/summary",
            tags=fastapi_tags,
            summary="Generate the Workload Summary",
        )
        async def post_workload_summary(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
        ):
            """
            Generate Workload Summary.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
            """
            try:
                ai_service.post_workload_summary(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating the Workload Summary for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while generating the Workload Summary for "
                        f"Workload {workload_name}"
                    ),
                ) from e

        @app.get(
            "/ai/workload/advanced",
            tags=fastapi_tags,
            summary="Get the Workload Advanced",
        )
        async def get_workload_advanced(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> WorkloadAdvanced:
            """
            Get the Workload Advanced.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

            Returns:
                WorkloadAdvanced: The Workload Advanced.
            """
            try:
                return ai_service.get_workload_advanced(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Workload Advanced for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Workload Advanced for "
                        f"Workload {workload_name}"
                    ),
                ) from e

        @app.post(
            "/ai/workload/advanced",
            tags=fastapi_tags,
            summary="Generate the Workload Advanced",
        )
        async def post_workload_advanced(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
        ):
            """
            Generate Workload Advanced.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
            """
            try:
                ai_service.post_workload_advanced(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating the Workload Advanced for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while generating the Workload Advanced for "
                        f"Workload {workload_name}"
                    ),
                ) from e

        @app.get(
            "/ai/workload/scores",
            tags=fastapi_tags,
            summary="Get the Workload Scores",
        )
        async def get_workload_scores(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> WorkloadScores:
            """
            Get the Workload Scores.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

            Returns:
                WorkloadScores: The Workload Scores.
            """
            try:
                return ai_service.get_workload_scores(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Workload Scores for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Workload Scores for "
                        f"Workload {workload_name}"
                    ),
                ) from e

        @app.post(
            "/ai/workload/scores",
            tags=fastapi_tags,
            summary="Generate the Workload Scores",
        )
        async def post_workload_scores(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
        ):
            """
            Generate Workload Scores.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
            """
            try:
                ai_service.post_workload_scores(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while generating the Workload Scores for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while generating the Workload Scores for "
                        f"Workload {workload_name}"
                    ),
                ) from e

        @app.put(
            "/ai/workload/fact",
            tags=fastapi_tags,
            summary="Add a Fact to the Workload",
        )
        async def put_workload_fact(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
                fact: Fact = Body(...),
        ):
            """
            Add a Fact to the Workload.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
                fact (Fact): The Fact to add.
            """
            try:
                ai_service.put_workload_fact(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                    fact,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while adding a Fact to Workload "
                        f"{workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while adding a Fact to Workload {workload_name}"
                    ),
                ) from e

        @app.delete(
            "/ai/workload/fact",
            tags=fastapi_tags,
            summary="Delete a Fact from the Workload",
        )
        async def delete_workload_fact(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
                fact: Fact = Body(...),
        ):
            """
            Delete a Fact from the Workload.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).
                fact (Fact): The Fact to delete.
            """
            try:
                ai_service.delete_workload_fact(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                    fact,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while deleting a Fact from Workload "
                        f"{workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while deleting a Fact from Workload {workload_name}"
                    ),
                ) from e

        @app.get(
            "/ai/workload/facts",
            tags=fastapi_tags,
            summary="Get the Workload Facts",
        )
        async def get_workload_facts(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> Facts:
            """
            Get the Workload Facts.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

            Returns:
                Facts: The Workload Facts.
            """
            try:
                return ai_service.get_workload_facts(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Workload Facts for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Workload Facts for "
                        f"Workload {workload_name}"
                    ),
                ) from e

        @app.get(
            "/ai/workload/topology",
            tags=fastapi_tags,
            summary="Get the Workload Topology",
        )
        async def get_workload_topology(
                cluster_name: str = Query(..., description="The Cluster name"),
                namespace: str = Query(..., description="The Namespace"),
                workload_name: str = Query(..., description="The Workload name"),
                kind: WorkloadKind = Query(..., description="The Workload kind"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> WorkloadTopology:
            """
            Get the Workload Topology.

            Args:
                cluster_name (str): The Cluster where the Workload is running.
                namespace (str): The Namespace where the Workload is running.
                workload_name (str): The Workload name.
                kind (WorkloadKind): The kind of Workload (Deployment, StatefulSet, etc.).

            Returns:
                WorkloadTopology: The Workload Topology.
            """
            try:
                return ai_service.get_workload_topology(
                    cluster_name,
                    namespace,
                    workload_name,
                    kind,
                )
            except Exception as e:
                logger.error(
                    (
                        f"An unexpected error occurred while retrieving the Workload Topology for "
                        f"Workload {workload_name}: {e}"
                    )
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"An error occurred while retrieving the Workload Topology for "
                        f"Workload {workload_name}"
                    ),
                ) from e
