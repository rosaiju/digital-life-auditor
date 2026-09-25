import json
from functools import lru_cache
from typing import Any

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from app.config import settings

_ENV_MAP = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}

MAX_SYNC_RESTARTS = 3


class PlaidError(Exception):
    """A Plaid API call failed. `message` is safe to show to the client."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


@lru_cache
def get_client() -> plaid_api.PlaidApi:
    configuration = plaid.Configuration(
        host=_ENV_MAP[settings.plaid_env],
        api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def _wrap(exc: plaid.ApiException) -> PlaidError:
    try:
        body = json.loads(exc.body)
        return PlaidError(body.get("error_message") or "Plaid request failed", body.get("error_code"))
    except (TypeError, ValueError):
        return PlaidError("Plaid request failed")


def _plain(obj: Any) -> Any:
    """Convert Plaid model objects into JSON-safe plain dicts (dates become strings)."""
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    return json.loads(json.dumps(obj, default=str))


def create_link_token(user_id: int) -> str:
    options = {}
    if settings.plaid_android_package_name:
        options["android_package_name"] = settings.plaid_android_package_name
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Digital Life Auditor",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=str(user_id)),
        **options,
    )
    try:
        return get_client().link_token_create(request)["link_token"]
    except plaid.ApiException as exc:
        raise _wrap(exc) from exc


def exchange_public_token(public_token: str) -> dict:
    try:
        response = get_client().item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        )
    except plaid.ApiException as exc:
        raise _wrap(exc) from exc
    return {"access_token": response["access_token"], "item_id": response["item_id"]}


def sync_transactions(access_token: str, cursor: str | None = None) -> dict:
    """Pull every page of /transactions/sync starting at `cursor`.

    Returns {"added": [...], "modified": [...], "removed": [ids], "cursor": str}.
    If the data changes mid-pagination Plaid asks us to restart from the original
    cursor, which we do a few times before giving up.
    """
    for _ in range(MAX_SYNC_RESTARTS):
        added: list[dict] = []
        modified: list[dict] = []
        removed: list[str] = []
        page_cursor = cursor or ""
        try:
            while True:
                response = get_client().transactions_sync(
                    TransactionsSyncRequest(access_token=access_token, cursor=page_cursor)
                )
                added += [_plain(t) for t in response["added"]]
                modified += [_plain(t) for t in response["modified"]]
                removed += [r["transaction_id"] for r in (_plain(r) for r in response["removed"])]
                page_cursor = response["next_cursor"]
                if not response["has_more"]:
                    return {"added": added, "modified": modified, "removed": removed, "cursor": page_cursor}
        except plaid.ApiException as exc:
            error = _wrap(exc)
            if error.code != "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION":
                raise error from exc
    raise PlaidError("Transactions kept changing during sync; try again shortly")


def remove_item(access_token: str) -> None:
    """Revoke the access token at Plaid (used when a user disconnects a bank)."""
    try:
        get_client().item_remove(ItemRemoveRequest(access_token=access_token))
    except plaid.ApiException as exc:
        raise _wrap(exc) from exc
