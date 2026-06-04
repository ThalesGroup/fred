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

"""Tests for the hello-world SDK surface."""

from fred_sdk.hello import hello_message


def test_hello_message_defaults_to_world() -> None:
    """Verify the hello-world API returns the default greeting.

    Why: Guard the public SDK contract for callers who omit a name.
    How: Call the function with an empty value and compare the output.
    """

    assert hello_message(None) == "Hello, world!"


def test_hello_message_trims_name() -> None:
    """Verify the hello-world API trims whitespace in the name.

    Why: Keep greetings predictable for agent authors passing user input.
    How: Provide a name with extra whitespace and compare the output.
    """

    assert hello_message("  Ada  ") == "Hello, Ada!"
