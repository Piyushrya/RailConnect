
from __future__ import annotations

from datetime import date, datetime
from typing import Any
import re

import requests
from bs4 import BeautifulSoup


NTES_HOME = "https://enquiry.indianrail.gov.in/mntes/"
NTES_RUNNING_URL = "https://enquiry.indianrail.gov.in/mntes/tr"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class LiveStatusError(RuntimeError):
    """An NTES request or parsing error suitable for display in Streamlit."""


def _clean(node: Any) -> str:
    """Extract readable text from a BeautifulSoup node."""
    if node is None:
        return ""
    return " ".join(node.stripped_strings)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _find_date_panel(
    soup: BeautifulSoup,
    journey_date: date,
) -> Any:
    """
    Find the panel corresponding to the requested journey date.

    NTES may change its panel IDs, so use both date-specific IDs
    and structural fallbacks. Do not silently return timetable data.
    """
    expected_id = (
        f"train{journey_date.day}-"
        f"{journey_date.strftime('%b').lower()}-"
        f"{journey_date.year}"
    ).lower()

    panels = [
        node
        for node in soup.find_all(id=True)
        if re.fullmatch(
            r"train\d{1,2}-[a-z]{3}-\d{4}",
            str(node.get("id", "")).lower(),
        )
    ]

    for panel in panels:
        if str(panel.get("id", "")).lower() == expected_id:
            return panel

    # Some NTES versions may use a different ID format. Look for
    # a date label near station rows rather than selecting an
    # arbitrary panel for another day.
    date_labels = {
        journey_date.strftime("%d-%b-%Y").lower(),
        journey_date.strftime("%d %b %Y").lower(),
        journey_date.strftime("%d-%B-%Y").lower(),
        journey_date.strftime("%d %B %Y").lower(),
    }

    for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "div", "span"]):
        label = _normalise(_clean(node)).lower()

        if label not in date_labels:
            continue

        candidate = node
        for _ in range(5):
            if candidate is None:
                break
            if candidate.select(".stopRow"):
                return candidate
            candidate = candidate.parent

    if panels:
        available = ", ".join(
            str(panel.get("id")) for panel in panels
        )
        raise LiveStatusError(
            f"NTES did not return the requested date "
            f"{journey_date.strftime('%d-%b-%Y')}. "
            f"Date panels found: {available}."
        )

    # Only accept a generic container if it contains actual station
    # rows. This helps diagnose markup changes without inventing data.
    station_rows = soup.select(".stopRow")
    if station_rows:
        raise LiveStatusError(
            "NTES returned station rows, but its date panel could "
            "not be identified safely. The page structure may have changed."
        )

    raise LiveStatusError(
        "NTES returned HTML, but no running-status station rows or "
        "date panels were found. The response may be an error page, "
        "a session page, or a changed NTES page format."
    )


def _read_time_column(column: Any) -> dict[str, str]:
    """Read scheduled/reported time text and any status badge."""
    result = {
        "scheduled": "",
        "reported": "",
        "status": "",
    }

    if column is None:
        return result

    spans = column.find_all("span", recursive=False)
    if not spans:
        spans = column.find_all("span")

    if spans:
        result["scheduled"] = _clean(spans[0].find("b") or spans[0])

    if len(spans) > 1:
        result["reported"] = _clean(spans[1].find("b") or spans[1])

    # Look for delay / early / on-time labels anywhere in the column.
    badge = column.select_one(".w3-round")
    if badge:
        result["status"] = _clean(badge)

    return result


def _parse_station_rows(panel: Any) -> list[dict[str, str]]:
    """Extract station details from NTES .stopRow elements."""
    results: list[dict[str, str]] = []

    for row in panel.select(".stopRow"):
        columns = row.find_all("div", recursive=False)

        if len(columns) < 3:
            continue

        arrival_column = columns[0]
        station_column = columns[2]

        nested = station_column.find_all("div", recursive=False)

        station_block = next(
            (
                item
                for item in nested
                if item.find("b") is not None
            ),
            station_column,
        )

        station_node = station_block.find("b")
        station_name = _clean(station_node)

        if not station_name:
            continue

        station_text = _clean(station_column)

        station_code = ""
        code_match = re.search(
            r"\b([A-Z0-9]{2,6})\b",
            station_text,
        )
        if code_match:
            station_code = code_match.group(1)

        distance = ""
        distance_match = re.search(
            r"\b(\d{1,5})\s*KM(?:S)?\b",
            station_text,
            flags=re.IGNORECASE,
        )
        if distance_match:
            distance = distance_match.group(1)

        platform = ""
        for badge in station_column.select(".w3-round"):
            badge_text = _clean(badge)
            if re.search(r"\bPF\b", badge_text, re.IGNORECASE):
                platform = badge_text
                break

        # Departure information may appear in a right-aligned child
        # of the station column in the NTES markup.
        departure_column = next(
            (
                item
                for item in nested
                if "text-align:right" in str(item.get("style", ""))
            ),
            None,
        )

        arrival = _read_time_column(arrival_column)
        departure = _read_time_column(departure_column)

        results.append({
            "station": station_name,
            "station_code": station_code,
            "platform": platform,
            "distance_km": distance,
            "scheduled_arrival": arrival["scheduled"],
            "reported_arrival": arrival["reported"],
            "arrival_status": arrival["status"],
            "scheduled_departure": departure["scheduled"],
            "reported_departure": departure["reported"],
            "departure_status": departure["status"],
        })

    if not results:
        raise LiveStatusError(
            "A date panel was found, but no station rows could be "
            "parsed. NTES may have changed its HTML layout."
        )

    return results


def parse_ntes_response(
    response_html: str,
    train_number: str,
    journey_date: date,
) -> dict[str, Any]:
    """Parse an NTES response into structured running-status data."""
    soup = BeautifulSoup(response_html, "html.parser")

    panel = _find_date_panel(soup, journey_date)

    heading = panel.select_one("h5, h4, h3, h2")
    train_title = _clean(heading) or f"Train {train_number}"
    train_title = re.sub(
        r"\s*Average Delay.*$",
        "",
        train_title,
        flags=re.IGNORECASE,
    ).strip()

    page_text = _clean(panel)

    journey_state = ""
    state_phrases = (
        "Yet to start from its source",
        "Train has arrived",
        "Train has been diverted",
        "Cancelled",
    )
    for phrase in state_phrases:
        if phrase.casefold() in page_text.casefold():
            journey_state = phrase
            break

    return {
        "train_number": train_number,
        "train_name": train_title,
        "running_date": journey_date.isoformat(),
        "fetched_at": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "journey_state": journey_state,
        "stations": _parse_station_rows(panel),
        "source": "NTES",
    }


def fetch_live_status(
    train_number: str,
    journey_date: date | str,
    timeout: int = 25,
) -> dict[str, Any]:
    """
    Fetch running-status data from NTES.

    Args:
        train_number: Numeric Indian Railways train number.
        journey_date: A datetime.date or ISO date such as '2026-10-26'.
        timeout: Request timeout in seconds.

    Returns:
        A dictionary containing train information and station rows.

    Raises:
        LiveStatusError: When the request fails or data cannot be parsed.
    """
    train_number = str(train_number).strip()

    if not re.fullmatch(r"\d{4,6}", train_number):
        raise LiveStatusError(
            "Enter a valid train number containing 4 to 6 digits."
        )

    if isinstance(journey_date, str):
        try:
            journey_date = date.fromisoformat(journey_date)
        except ValueError as exc:
            raise LiveStatusError(
                "Journey date must be in YYYY-MM-DD format."
            ) from exc

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })

    try:
        landing = session.get(NTES_HOME, timeout=timeout)
        landing.raise_for_status()
    except requests.RequestException as exc:
        raise LiveStatusError(
            f"Could not establish an NTES session: {exc}"
        ) from exc

    landing_soup = BeautifulSoup(landing.text, "html.parser")

    # Carry over hidden form fields where NTES provides them.
    payload: dict[str, str] = {}

    form = (
        landing_soup.find("form", attrs={"name": "frmTRN"})
        or landing_soup.find("form")
    )

    if form:
        for field in form.find_all("input", attrs={"type": "hidden"}):
            field_name = field.get("name")
            if field_name:
                payload[field_name] = field.get("value", "")

    payload.update({
        "opt": "TrainRunning",
        "subOpt": "FindRunningInstance",
        "lan": "en",
        "jDate": journey_date.strftime("%d-%b-%Y"),
        "trainNo": train_number,
    })

    try:
        response = session.post(
            NTES_RUNNING_URL,
            params={
                "opt": "TrainRunning",
                "subOpt": "FindRunningInstance",
            },
            data=payload,
            headers={
                "Referer": NTES_HOME,
                "Origin": "https://enquiry.indianrail.gov.in",
            },
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LiveStatusError(
            f"NTES running-status request failed: {exc}"
        ) from exc

    content_type = response.headers.get("Content-Type", "").lower()

    if "html" not in content_type and not response.text.strip().startswith("<"):
        raise LiveStatusError(
            "NTES returned an unexpected response type instead of HTML."
        )

    try:
        return parse_ntes_response(
            response.text,
            train_number,
            journey_date,
        )
    except LiveStatusError:
        raise
    except Exception as exc:
        raise LiveStatusError(
            f"Could not parse the NTES response: {exc}"
        ) from exc
