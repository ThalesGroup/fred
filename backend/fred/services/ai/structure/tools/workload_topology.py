import requests
from langchain_core.tools import StructuredTool
from openai import BaseModel
from pydantic import Field

from services.ai.structure.workload_topology import WorkloadTopology


class WorkoadTopologyInput(BaseModel):
    """
    The input to the workload topology tool
    """

    cluster_fullname: str = Field(description="The fullname of the cluster")
    namespace: str = Field(description="The namespace of the workload")
    workload_name: str = Field(description="The name of the workload")
    workload_kind: str = Field(description="The Kubernetes kind of the workload")


def get_workload_topology(
    cluster_fullname: str, namespace: str, workload_name: str, workload_kind: str
) -> WorkloadTopology:
    """
    This tool retrieves detailed information about a specific Kubernetes workload. Use this tool if the user asks specific questions about any Kubernetes workload, such as its configuration, status, resource usage, or events associated with it.
    """
    url = "http://localhost:8000/fred/ai/workload/topology"
    response = requests.get(
        url,
        params={
            "cluster_name": cluster_fullname,
            "namespace": namespace,
            "workload_name": workload_name,
            "kind": workload_kind,
        },
        timeout=120,
    )

    return response.json()


get_workload_topology_tool = StructuredTool.from_function(
    func=get_workload_topology,
    name="get_workload_topology",
    description="Retrieves detailed information about a specific Kubernetes workload. Use this tool if the user asks specific questions about any Kubernetes workload, such as its configuration, status, resource usage, or events associated with it.",
    return_direct=True,
)
