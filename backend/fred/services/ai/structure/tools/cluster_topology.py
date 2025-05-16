import requests
from langchain_core.tools import StructuredTool
from openai import BaseModel
from pydantic import Field

from services.ai.structure import cluster_topology


class ClusterTopologyInput(BaseModel):
    """
    The input to the cluster topology tool
    """

    cluster_fullname: str = Field(description="The fullname of the cluster")


def get_cluster_topology(cluster_fullname: str) -> cluster_topology:
    """
    "Retrieves a condensed representation of a Kubernetes cluster. Use this tools if the user asks questions about a Kubernetes cluster."
    """
    url = "http://localhost:8000/fred/ai/cluster/topology"
    response = requests.get(
        url,
        params={
            "cluster_name": cluster_fullname,
        },
        timeout=120,
    )

    return response.json()


get_cluster_topology_tool = StructuredTool.from_function(
    func=get_cluster_topology,
    name="get_cluster_topology",
    description="Retrieves a condensed representation of a Kubernetes cluster. Use this tools if the user asks questions about a Kubernetes cluster.",
    args_schema=ClusterTopologyInput,
    return_direct=True,
)
