
"""ConfirmTkt PNR status integration for RailConnect.

The endpoint and request format are based on an unofficial,
community-maintained reference. Availability is not guaranteed.
"""

import re
import uuid

import requests


PNR_API_URL = (
    "https://cttrainsapi.confirmtkt.com"
    "/api/v2/ctpro/mweb/{pnr}"
)
TIMEOUT_SECONDS = 20


def get_pnr_status(pnr_number: str) -> dict:
    """Fetch PNR status and return the provider's JSON response."""

    pnr = str(pnr_number).strip()

    if not re.fullmatch(r"\d{10}", pnr):
        raise ValueError("Please enter a valid 10-digit PNR number.")

    url = PNR_API_URL.format(pnr=pnr)
    params = {
        "querysource": "ct-web",
        "locale": "en",
        "getHighChanceText": "true",
        "livePnr": "false",
    }

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.confirmtkt.com",
        "Referer": "https://www.confirmtkt.com/",
        "ClientId": "ct-web",
        "ApiKey": "ct-web!2$",
        "DeviceId": str(uuid.uuid4()),
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    payload = {
        "proPlanName": "CP7",
        "emailId": "",
        "tempToken": "",
    }

    try:
        response = requests.post(
            url,
            params=params,
            headers=headers,
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )

        if response.status_code in (401, 403, 405, 429):
            raise RuntimeError(
                f"ConfirmTkt rejected the request (HTTP "
                f"{response.status_code}). The endpoint may require "
                "authorized credentials or may no longer be available."
            )

        response.raise_for_status()

    except requests.Timeout as exc:
        raise RuntimeError(
            "ConfirmTkt took too long to respond. Please try again."
        ) from exc

    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not retrieve PNR status from ConfirmTkt: {exc}"
        ) from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "ConfirmTkt returned a non-JSON response. "
            "The endpoint may have changed or returned a security page."
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError("ConfirmTkt returned an unexpected response.")

    pnr_response = result.get("data", {}).get("pnrResponse", {})

    if not isinstance(pnr_response, dict):
        raise RuntimeError("ConfirmTkt returned an unexpected PNR format.")

    if pnr_response.get("error"):
        raise RuntimeError(
            f"ConfirmTkt could not retrieve this PNR: "
            f"{pnr_response['error']}"
        )

    return result
