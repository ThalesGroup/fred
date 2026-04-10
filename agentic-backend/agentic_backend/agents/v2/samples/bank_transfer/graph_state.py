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

"""
Input and state models for the Bank Transfer graph agent sample.

This file shows what starts a transfer session and what the workflow remembers
while it classifies intent, validates the source account, checks compliance,
evaluates risk, and executes the transfer through two HITL confirmation gates.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BankTransferInput(BaseModel):
    """
    User message that starts one bank transfer session.

    Example:
    ```python
    request = BankTransferInput(
        message="Transfer 500 EUR from ACC-001 to ACC-002",
    )
    ```
    """

    message: str = Field(..., min_length=1)


class BankTransferState(BaseModel):
    """
    Business state carried through the bank transfer workflow.

    Fields progress from raw user intent (source, destination, amount) through
    account validation, KYC compliance, risk evaluation, and the committed
    transaction. Each step reads what it needs and writes only its own outputs.

    Example:
    ```python
    state = BankTransferState(
        latest_user_text="Transfer 500 EUR from ACC-001 to ACC-002",
        source_account_id="ACC-001",
        destination_account_id="ACC-002",
        transfer_amount=500.0,
    )
    ```
    """

    latest_user_text: str

    # Transfer parameters extracted from the user message by the intent step
    source_account_id: str | None = None
    destination_account_id: str | None = None
    transfer_amount: float | None = None

    # Source account details loaded from bank-core (holder name, balance, currency)
    source_account: dict[str, object] | None = None

    # Risk evaluation result from risk-guard
    risk_score: int | None = None
    risk_reason: str | None = None

    # Pending transaction created by prepare_transfer (PENDING_APPROVAL status)
    transaction_id: str | None = None
    transaction_currency: str | None = None

    # Terminal output written by the last meaningful step
    final_text: str | None = None
    done_reason: str | None = None
