# Copyright Thales 2026
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

"""Package the Weaver model from the Control Plane source; never edit the copy."""

from pathlib import Path
from shutil import copyfile

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.editable_wheel import editable_wheel
from setuptools.command.sdist import sdist

ROOT = Path(__file__).resolve().parent
RESOURCE = ROOT / "fred_core/security/rebac/weaver-model.json"
SOURCE = ROOT.parent.parent / "apps/control-plane/openfga/model.json"


def prepare_weaver_model() -> None:
    """Refresh from the checkout, or retain the resource supplied by the sdist/image."""
    if SOURCE.is_file():
        copyfile(SOURCE, RESOURCE)
    elif not RESOURCE.is_file():
        raise FileNotFoundError(
            "Canonical Weaver model missing: build from the Fred checkout or a complete sdist"
        )


class BuildPy(build_py):
    def run(self) -> None:
        prepare_weaver_model()
        super().run()


class Sdist(sdist):
    def run(self) -> None:
        prepare_weaver_model()
        super().run()


class EditableWheel(editable_wheel):
    def run(self) -> None:
        prepare_weaver_model()
        super().run()


setup(cmdclass={"build_py": BuildPy, "sdist": Sdist, "editable_wheel": EditableWheel})
