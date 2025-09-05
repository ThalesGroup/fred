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

import functools
from typing import Callable

from .authorization import Action, Resource
from .authorization import authorize as authz_check
from .structure import KeycloakUser


def authorize(action: Action, resource: Resource):
    """
    Decorator to authorize service method calls.

    The decorated method must have a 'user' parameter of type KeycloakUser.

    Usage:
        @authorize(Action.READ, Resource.DOCUMENTS)
        def get_documents(self, user: KeycloakUser) -> List[Document]:
            return self.document_store.get_all()
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Find the user parameter
            user = None

            # Check positional args
            for arg in args:
                if isinstance(arg, KeycloakUser):
                    user = arg
                    break

            # Check keyword args
            if user is None and "user" in kwargs:
                user = kwargs["user"]

            if user is None:
                raise ValueError(
                    f"Method {func.__name__} decorated with @authorize must have a 'user: KeycloakUser' parameter"
                )

            print(f"\n\nchecking {user.username} for {action} on {resource}\n\n\n")
            # Perform authorization check
            authz_check(user, action, resource)

            # Call the original function
            return func(*args, **kwargs)

        return wrapper

    return decorator
