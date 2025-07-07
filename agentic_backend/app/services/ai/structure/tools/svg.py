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
