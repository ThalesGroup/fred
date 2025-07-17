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

import logging
import os
import shutil
import traceback
from datetime import datetime

from app.features.frugal.cluster_consumption.cluster_consumption_service import ClusterConsumptionService
from app.features.k8.kube_service import ClusterList, KubeService
from app.services.frontend.frontend_structures import ClusterDescription, ClusterFootprint, ClusterScore, NamespaceDescription, Observation, WorkloadDescription, WorkloadScore
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from app.application_context import get_app_context, get_configuration

from fred_core import KeycloakUser, get_current_user
from app.features.frugal.ai_service import AIService, WorkloadKind
from app.common.connectors.file_dao import FileDAO

from app.common.structure import (
    DAOTypeEnum,
    OfflineStatus,
    PrecisionEnum,
)
logger = logging.getLogger(__name__)

class UiController:
    """
    This controller is responsible for handling the UI HTTP endpoints and
    WebSocket endpoints. It uses the KubeService and AIService to provide
    the necessary information to the UI.

    It is paramount importance to not pollute the low level controller with
    high level logic. This controller is responsible for handling the UI
    specific logic and should not contain any low level logic.
    """

    def __init__(self, app: APIRouter,kube_service: KubeService,  ai_service: AIService):
        self.ai_service =ai_service
        self.kube_service = kube_service
        self.cluster_consumption_service = ClusterConsumptionService()

        # For import-export operations
        match get_configuration().dao.type:
            case DAOTypeEnum.file:
                self.dao = FileDAO(get_configuration().dao)
            case dao_type:
                raise NotImplementedError(f"DAO type {dao_type}")

        fastapi_tags = ["UI service"]

        def delete_file(file_path: str):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Failed to delete file {file_path}: {e}")

        @app.get("/export", tags=fastapi_tags, summary="Export a dump of the data")
        async def export_data(background_tasks: BackgroundTasks, user: KeycloakUser = Depends(get_current_user)):
            """
            Export the data as a zip file.

            Returns:
                StreamingResponse: The zip file containing the data.
            """
            try:
                zip_path = self.dao.export_all("/tmp")

                # Generator to read the zip file in chunks
                def iter_file(file_path):
                    with open(file_path, "rb") as f:
                        while chunk := f.read(1024 * 1024):  # 1 MB chunks
                            yield chunk

                background_tasks.add_task(delete_file, zip_path)

                return StreamingResponse(
                    iter_file(zip_path),
                    media_type="application/zip",
                    headers={
                        "Content-Disposition": f'attachment; filename={zip_path.split("/")[-1]}'
                    },
                )
            except Exception as e:
                logger.error(
                    f"An unexpected error occurred while exporting the data: {e}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"An error occurred while exporting data: {e}",
                ) from e

        @app.put("/import", tags=fastapi_tags, summary="Import a dump of the data")
        async def import_data(
            background_tasks: BackgroundTasks, file: UploadFile = File(...)
        ):
            """
            Import data from a zip file.
            """
            zip_path = f"/tmp/{file.filename}"

            try:
                # Save the uploaded zip file to a temporary location
                with open(zip_path, "wb") as temp_file:
                    shutil.copyfileobj(file.file, temp_file)

                # Import the data using the `import_all` method of `self.dao`
                self.dao.import_all(zip_path)

                background_tasks.add_task(delete_file, zip_path)

            except Exception as e:
                logging.error(
                    f"An unexpected error occurred while importing the data: {e}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"An error occurred while importing data: {e}",
                ) from e

        @app.put(
            "/toggle_offline",
            tags=fastapi_tags,
            summary="Toggle the service's online/offline status",
            description=(
                "This endpoint allows toggling the online/offline status of the service. "
                "When `is_offline` is set to `true`, the services go into offline mode and "
                "is unavailable for regular operations. You will need a previous dump of the data"
                "When `is_offline` is set to `false`, the services become available and are initialized "
                "if they have not been already. "
                "This setting applies globally across all service instances."
                "By default, the offline mode is disabled, so you are online."
            ),
        )
        async def toggle_offline(toggle_status: OfflineStatus) -> OfflineStatus:
            app_context = get_app_context()
            if toggle_status.is_offline:
                app_context.status.enable_offline()
            else:
                app_context.status.disable_offline()
            return toggle_status

        @app.get(
            "/clusters/footprints",
            tags=fastapi_tags,
            description="Get the details of all clusters in carbon, energy and cost consumption for a given time range",
            summary="Get the details of all clusters in carbon, energy and cost consumption for a given time range",
        )
        async def get_clusters_footprints(
            start: datetime, end: datetime, precision: PrecisionEnum = PrecisionEnum.D,
            user: KeycloakUser = Depends(get_current_user)
        ) -> list[ClusterFootprint]:
            logger.info(f"User {user.username} with roles {user.roles} is fetching cluster footprints")

            if start >= end:
                raise HTTPException(
                    status_code=400, detail="Start date must be before end date"
                )
            try:
                cluster_footprints: list[ClusterFootprint] = []
                clusters: ClusterList = self.kube_service.get_clusters_list()

                for cluster in clusters.clusters_list:
                    # Initialize values for carbon, energy, and financial consumption with defaults
                    carbon_consumption_value, carbon_consumption_unit = -1, "gco2"
                    energy_consumption_value, energy_consumption_unit = -1, "wh"
                    financial_consumption_value, financial_consumption_unit = -1, "USD"

                    try:
                        # Attempt to get carbon consumption data
                        carbon_consumption = (
                            self.cluster_consumption_service.consumption_gco2(
                                start, end, cluster.alias, precision
                            )
                        )
                        (carbon_consumption_value, carbon_consumption_unit) = (
                            carbon_consumption.auc,
                            carbon_consumption.unit,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to retrieve carbon consumption for cluster {cluster.alias}: {e}"
                        )

                    try:
                        # Attempt to get energy consumption data
                        energy_consumption = (
                            self.cluster_consumption_service.consumption_wh(
                                start, end, cluster.alias, precision
                            )
                        )
                        (energy_consumption_value, energy_consumption_unit) = (
                            energy_consumption.auc,
                            energy_consumption.unit,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to retrieve energy consumption for cluster {cluster.alias}: {e}"
                        )

                    try:
                        # Attempt to get financial consumption data
                        financial_consumption = (
                            self.cluster_consumption_service.consumption_finops(
                                start, end, cluster.alias, precision
                            )
                        )
                        (financial_consumption_value, financial_consumption_unit) = (
                            financial_consumption.auc,
                            financial_consumption.unit,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to retrieve financial consumption for cluster {cluster.alias}: {e}"
                        )

                    # Create the ClusterFootprint object with the retrieved or default values
                    cluster_footprint = ClusterFootprint(
                        cluster=cluster,
                        carbon=Observation(
                            value=carbon_consumption_value, unit=carbon_consumption_unit
                        ),
                        energy=Observation(
                            value=energy_consumption_value, unit=energy_consumption_unit
                        ),
                        cost=Observation(
                            value=financial_consumption_value,
                            unit=financial_consumption_unit,
                        ),
                    )
                    cluster_footprints.append(cluster_footprint)

                return cluster_footprints

            except Exception as e:
                logger.error(str(e))
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=str(e))

        @app.get(
            "/ui/scores",
            tags=fastapi_tags,
            summary="Get the global audit of a cluster. "
            "Audit provides an easy tree structure to navigate the cluster inner components scores and an global score.",
        )
        async def get_cluster_scores(
            cluster_name: str = Query(..., description="The identifier of the cluster"),
            user: KeycloakUser = Depends(get_current_user)
        ) -> ClusterScore:
            known_clusters: ClusterList = self.kube_service.get_clusters_list()
            target_cluster = next(
                (c for c in known_clusters.clusters_list if c.fullname == cluster_name),
                None,
            )
            if target_cluster is None:
                raise HTTPException(
                    status_code=404, detail=f"Cluster {cluster_name} not found"
                )
            try:
                workload_scores = []
                namespaces = self.kube_service.get_namespaces_list(cluster_name)
                for namespace in namespaces.namespaces:
                    for workload_kind in WorkloadKind:
                        try:
                            workload_name_list = (
                                self.kube_service.get_workload_names_list(
                                    cluster_name, namespace, workload_kind
                                )
                            )
                            for workload_name in workload_name_list.workloads:
                                scores = self.ai_service.get_workload_scores(
                                    cluster_name,
                                    namespace,
                                    workload_name,
                                    workload_kind,
                                )
                                workload_scores.append(
                                    WorkloadScore(
                                        name=workload_name,
                                        namespace=namespace,
                                        kind=workload_kind,
                                        scores=scores,
                                    )
                                )
                        except FileNotFoundError:
                            # Log and continue if no workloads of this kind are found
                            logger.debug(
                                f"No {workload_kind.value} workloads found in namespace {namespace}."
                            )
                            continue
                # Return a Cluster score, simply listing all the workload scores
                return ClusterScore(
                    cluster=cluster_name,
                    alias=target_cluster.alias,
                    workload_scores=workload_scores,
                )
            except Exception as e:
                logger.error(str(e))
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=str(e))

        @app.get(
            "/ui/details",
            tags=fastapi_tags,
            summary="Get the details about a cluster. "
            "Details provides an easy tree structure to navigate the cluster inner components.",
        )
        async def get_cluster_details(
            cluster_name: str = Query(..., description="The identifier of the cluster"),
            user: KeycloakUser = Depends(get_current_user)
        ) -> ClusterDescription:
            known_clusters: ClusterList = self.kube_service.get_clusters_list()
            target_cluster = next(
                (c for c in known_clusters.clusters_list if c.fullname == cluster_name),
                None,
            )
            if target_cluster is None:
                raise HTTPException(
                    status_code=404, detail=f"Cluster {cluster_name} not found"
                )
            try:
                namespaces = self.kube_service.get_namespaces_list(cluster_name)
                namepace_workloads = []
                for namespace in namespaces.namespaces:
                    workload_descriptions = []
                    for workload_kind in WorkloadKind:
                        try:
                            workload_name_list = (
                                self.kube_service.get_workload_names_list(
                                    cluster_name, namespace, workload_kind
                                )
                            )
                            for workload_name in workload_name_list.workloads:
                                factList = self.ai_service.get_workload_facts(
                                    cluster_name,
                                    namespace,
                                    workload_name,
                                    workload_kind,
                                )
                                workload_descriptions.append(
                                    WorkloadDescription(
                                        name=workload_name,
                                        kind=workload_kind,
                                        facts=factList.facts,
                                    )
                                )
                        except FileNotFoundError:
                            # Log and continue if no workloads of this kind are found
                            logger.info(
                                f"No {workload_kind.value} workloads found in namespace {namespace}."
                            )
                            continue

                    namespace_facts = self.ai_service.get_namespace_facts(
                        cluster_name, namespace
                    )
                    namepace_workloads.append(
                        NamespaceDescription(
                            name=namespace,
                            workloads=workload_descriptions,
                            facts=namespace_facts.facts,
                        )
                    )
                cluster_facts = self.ai_service.get_cluster_facts(cluster_name)
                # Return a Cluster object, passing arguments as keywords
                return ClusterDescription(
                    cluster=cluster_name,
                    alias=target_cluster.alias,
                    namespaces=namepace_workloads,
                    facts=cluster_facts.facts,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
