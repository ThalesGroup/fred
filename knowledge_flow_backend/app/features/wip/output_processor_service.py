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

import pathlib
from app.application_context import ApplicationContext
from app.common.structures import OutputProcessorResponse


class OutputProcessorService:
    """
    Output Processor Service
    ------------------------------------------------------
    This service in charge of invoking the right output processing function.
    It is very simple it just calls the processor class with the right parameters.

    By default, all markdown and tabular files are processed. Markdown files
    are processed using the default VectorizationPipeline, while tabular files
    are processed using the TabularPipeline.

    These processors can be replaced by custom processors
    by implementing the `BaseOutputProcessor` interface and registering them
    in the `ApplicationContext`.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()

    def process(self, working_dir: pathlib.Path, input_file: str, input_file_metadata: dict) -> OutputProcessorResponse:
        """
        Processes data resulting from the input processing.
        """
        suffix = pathlib.Path(input_file).suffix.lower()
        processor = self.context.get_output_processor_instance(suffix)
        # check the content of the working dir 'output' directory and if there are some 'output.md' or 'output.csv' files
        # get their path and pass them to the processor
        output_dir = working_dir / "output"
        if not output_dir.exists():
            raise ValueError(f"Output directory {output_dir} does not exist")
        if not output_dir.is_dir():
            raise ValueError(f"Output directory {output_dir} is not a directory")
        # check if the output_dir contains "output.md" or "output.csv" files
        if not any(output_dir.glob("*.*")):
            raise ValueError(f"Output directory {output_dir} does not contain output files")
        # get the first file in the output_dir
        output_file = next(output_dir.glob("*.*"))
        # check if the file is a markdown or csv file
        if output_file.suffix.lower() not in [".md", ".csv"]:
            raise ValueError(f"Output file {output_file} is not a markdown or csv file")
        # check if the file is empty
        if output_file.stat().st_size == 0:
            raise ValueError(f"Output file {output_file} is empty")
        # check if the file is a markdown or csv file
        return processor.process(output_file, input_file_metadata)
