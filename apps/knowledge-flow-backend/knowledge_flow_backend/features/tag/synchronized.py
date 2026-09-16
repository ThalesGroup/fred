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

"""Whether a folder is filled by a machine, and what that forbids a person.

One folder in a library carries the mark — the one the library starts at — and
everything nested under it derives its answer from that root, so the two can
never disagree. Every caller asks here rather than reading the field, which is
what keeps the rule in one place while the sites enforcing it are spread out.
"""

from __future__ import annotations

from fred_core import KeycloakUser
from fred_core.security.structure import is_service_agent

from knowledge_flow_backend.core.stores.tags.base_tag_store import TagNotFoundError
from knowledge_flow_backend.features.tag.structure import Tag


class FolderIsSynchronized(Exception):
    """A person tried to change what a machine fills.

    Distinct from being unauthorized: the caller may well hold the right, and
    the answer they need is which base owns this folder.
    """

    def __init__(self, machine: str) -> None:
        super().__init__(f"This folder is filled by {machine}, so its contents are not editable here.")
        self.machine = machine


async def synchronizing_machine(tag_store, tag: Tag) -> str | None:
    """Which machine fills the library this folder belongs to, if any.

    A folder at the top of a corpus answers for itself. Anything nested resolves
    its root by the first segment of its path — safe because a marked root is
    created with a validated single-segment name, so the segment is the whole
    name and the lookup cannot land elsewhere.
    """
    if tag.path is None:
        return tag.synchronized_by

    root_name = tag.path.split("/")[0]
    root = await tag_store.get_by_owner_type_full_path(
        owner_id=tag.owner_id,
        tag_type=tag.type,
        full_path=root_name,
    )
    return root.synchronized_by if root is not None else None


async def refuse_if_synchronized(tag_store, tag: Tag, user: KeycloakUser) -> None:
    """Stop a person changing what a machine fills; let the machine through.

    Called after the caller's right over this folder has been checked, so that
    holding no right is still reported as holding no right and a refusal here
    tells a legitimate caller something they can act on.
    """
    if is_service_agent(user):
        return
    machine = await synchronizing_machine(tag_store, tag)
    if machine is not None:
        raise FolderIsSynchronized(machine)


async def refuse_if_synchronized_by_id(tag_store, tag_id: str, user: KeycloakUser) -> None:
    """The same guard for a caller holding only the folder's id."""
    if is_service_agent(user):
        return
    try:
        tag = await tag_store.get_tag_by_id(tag_id)
    except TagNotFoundError:
        # Nothing to protect, and the caller's own path reports the absence
        # better than this guard could.
        return
    await refuse_if_synchronized(tag_store, tag, user)
