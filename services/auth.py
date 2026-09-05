"""Demo sign-in and role separation.

**This is not a security system.** It exists so the demo can show two different
audiences using the same agent:

* a **buyer**, who submits their own inquiry and sees only their own lead;
* a **broker**, who sees the whole pipeline, every lead and the inventory.

There are no user accounts, no password storage and no session tokens. A buyer
signs in with a display name alone; broker access is gated by a single shared
access code so the two experiences stay separate during a demo. Anyone with the
code gets broker access, and the code is read from the environment in plain
text. Do not put real data behind it.

A real deployment would replace this module entirely with an identity provider.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

# The default is published in .env.example and the README: it is a demo latch,
# not a secret. Override it with BROKER_ACCESS_CODE to change it locally.
DEFAULT_BROKER_CODE = "broker123"

BUYER = "buyer"
BROKER = "broker"


@dataclass(frozen=True)
class Account:
    """Who is using the app right now."""

    username: str  # normalised key used as the lead owner
    display_name: str
    role: str

    @property
    def is_broker(self) -> bool:
        return self.role == BROKER

    @property
    def role_label(self) -> str:
        return "Broker" if self.is_broker else "Buyer"


class SignInError(ValueError):
    """The sign-in details were unusable."""


def broker_access_code() -> str:
    return os.getenv("BROKER_ACCESS_CODE", DEFAULT_BROKER_CODE).strip() or DEFAULT_BROKER_CODE


def normalise_username(display_name: str) -> str:
    """Turn a typed name into a stable key for lead ownership.

    Two people who type "Rahul Nair" and "rahul  nair" are the same demo
    account; that is intentional, and another reason this is not real auth.
    """
    text = unicodedata.normalize("NFKD", display_name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return text


def sign_in_buyer(display_name: str) -> Account:
    display_name = (display_name or "").strip()
    if len(display_name) < 2:
        raise SignInError("Enter your name (at least 2 characters) to continue.")
    if len(display_name) > 60:
        raise SignInError("That name is too long; please shorten it.")
    username = normalise_username(display_name)
    if not username:
        raise SignInError("Please use letters or numbers in your name.")
    return Account(username=username, display_name=display_name, role=BUYER)


def sign_in_broker(display_name: str, access_code: str) -> Account:
    display_name = (display_name or "").strip() or "Broker"
    if (access_code or "").strip() != broker_access_code():
        raise SignInError("That broker access code is not correct.")
    return Account(
        username=normalise_username(display_name) or "broker",
        display_name=display_name,
        role=BROKER,
    )


def sign_in(role: str, display_name: str, access_code: str = "") -> Account:
    """Sign in as ``BUYER`` or ``BROKER``. Raises :class:`SignInError`."""
    if role == BROKER:
        return sign_in_broker(display_name, access_code)
    if role == BUYER:
        return sign_in_buyer(display_name)
    raise SignInError(f"Unknown role {role!r}.")


# --------------------------------------------------------------------------- #
# Streamlit session helpers
# --------------------------------------------------------------------------- #
SESSION_KEY = "account"


def current_account(session) -> Optional[Account]:
    account = session.get(SESSION_KEY)
    return account if isinstance(account, Account) else None


def store_account(session, account: Account) -> None:
    session[SESSION_KEY] = account


def sign_out(session) -> None:
    """Clear the account and every piece of per-user state it produced."""
    for key in (
        SESSION_KEY, "active_lead_id", "last_result", "agent_error",
        "last_turn_seconds", "pending_view", "active_view", "buyer_view",
    ):
        session.pop(key, None)
    session["clear_lead_inputs"] = True
