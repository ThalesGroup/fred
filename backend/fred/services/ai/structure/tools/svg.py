from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class SvgInput(BaseModel):
    """
    The input used to render an SVG
    """

    svg_code: str = Field(
        description="The markdown base64 encoded SVG (width 600px). Make sure the texts and labels are readable and clear."
    )


def get_svg(svg_code: SvgInput) -> str:
    """
    Get the markdown base64 encoded SVG
    """
    return svg_code


get_svg_tool = StructuredTool.from_function(
    func=get_svg,
    name="get_svg",
    description="Get the markdown base64 encoded SVG",
    args_schema=SvgInput,
    return_direct=True,
)
