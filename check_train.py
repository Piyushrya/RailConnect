
"""Qrail PNR status integration for RailConnect."""

import os
import re

import requests
from dotenv import load_dotenv

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

QRAIL_API_KEY = os.getenv("QRAIL_API_KEY", "").strip()
QRAIL_PNR_URL = "https://api.qrail.in/api/v1/trains/pnr/status"
TIMEOUT_SECONDS = 20


def get_pnr_status(pnr_number: str) -> dict:
    """Fetch PNR status from Qrail."""

    pnr = str(pnr_number).strip()

    if not re.fullmatch(r"\d{10}", pnr):
        raise ValueError("Please enter a valid 10-digit PNR number.")

    if not QRAIL_API_KEY:
        raise RuntimeError(
            "QRAIL_API_KEY is missing. "
            "Add your Qrail API key to the .env file."
        )

    headers = {
        "Authorization": f"Bearer {QRAIL_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # The screenshot shows a "train" field, but its use for PNR
    # lookup must be confirmed with Qrail.
    payload = {"train": pnr}

    try:
        response = requests.post(
            QRAIL_PNR_URL,
            headers=headers,
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()

    except requests.HTTPError as exc:
        status_code = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )

        if status_code in (401, 403):
            raise RuntimeError(
                "Qrail rejected the API key or denied access. "
                "Check your key and plan permissions."
            ) from exc

        if status_code == 429:
            raise RuntimeError(
                "Qrail request limit reached. Please try again later."
            ) from exc

        error_text = (
            exc.response.text[:500]
            if exc.response is not None
            else str(exc)
        )
        raise RuntimeError(
            f"Qrail returned HTTP {status_code}: {error_text}"
        ) from exc

    except requests.RequestException as exc:
        raise RuntimeError(f"Could not connect to Qrail: {exc}") from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Qrail returned a response that was not valid JSON."
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError("Qrail returned an unexpected response format.")

    return result
