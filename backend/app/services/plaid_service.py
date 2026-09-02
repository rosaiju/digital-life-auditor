from datetime import date, timedelta

import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.country_code import CountryCode
from plaid.model.products import Products

from app.config import settings

_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "development": plaid.Environment.Development,
    "production": plaid.Environment.Production,
}

configuration = plaid.Configuration(
    host=_ENV_MAP.get(settings.plaid_env, plaid.Environment.Sandbox),
    api_key={
        "clientId": settings.plaid_client_id,
        "secret": settings.plaid_secret,
    },
)
api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)


def create_link_token(user_id: int) -> str:
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Digital Life Auditor",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=str(user_id)),
    )
    response = client.link_token_create(request)
    return response["link_token"]


def exchange_public_token(public_token: str) -> dict:
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(request)
    return {
        "access_token": response["access_token"],
        "item_id": response["item_id"],
    }


def sync_transactions(access_token: str, cursor: str | None = None) -> dict:
    """
    Uses Plaid's /transactions/sync endpoint.
    Returns added transactions and updated cursor.
    """
    added = []
    has_more = True

    while has_more:
        request = TransactionsSyncRequest(
            access_token=access_token,
            cursor=cursor or "",
        )
        response = client.transactions_sync(request)
        added.extend(response["added"])
        cursor = response["next_cursor"]
        has_more = response["has_more"]

    return {"transactions": added, "cursor": cursor}


def get_institution_name(item_id: str) -> str | None:
    try:
        from plaid.model.item_get_request import ItemGetRequest
        from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest

        item_response = client.item_get(ItemGetRequest(access_token=""))
        institution_id = item_response["item"]["institution_id"]
        inst_response = client.institutions_get_by_id(
            InstitutionsGetByIdRequest(
                institution_id=institution_id,
                country_codes=[CountryCode("US")],
            )
        )
        return inst_response["institution"]["name"]
    except Exception:
        return None
