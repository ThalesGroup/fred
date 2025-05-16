from langchain_core.tools import BaseToolkit, StructuredTool
from pydantic import BaseModel, Field


class ClusterTopologyArgs(BaseModel):
    """
    Arguments for the get_cluster_topology function
    """

    cluster_fullname: str = Field(description="The fullname of the cluster")


def wrapper(ai_service):
    def get_cluster_topology(cluster_fullname: str) -> str:
        """
        "Retrieves a condensed representation of a Kubernetes cluster"
        """
        return ai_service.get_cluster_topology(cluster_fullname)

    return get_cluster_topology


class TechnicalKubernetesToolkit(BaseToolkit):
    """
    The technical Kubernetes toolkit
    """

    tools: list = Field(
        default_factory=list, description="List of tools in the toolkit."
    )

    def get_tools(self):
        return self.tools


class TechnicalKubernetesToolkitBuilder:
    def __init__(self, ai_service):
        self.ai_service = ai_service

    def build(self):
        func = wrapper(ai_service=self.ai_service)
        tool = StructuredTool.from_function(
            func=func,
            name="get_cluster_topology",
            description="Retrieves a condensed representation of a Kubernetes cluster.",
            args_schema=ClusterTopologyArgs,
            return_direct=True,
        )
        return TechnicalKubernetesToolkit(tools=[tool])
