"""RailConnect train availability page.

Uses the observed train-search endpoint and keeps live results distinct from
local timetable data. The upstream endpoint may change or restrict requests.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from html import escape
from typing import Any

import requests
import streamlit as st

TIMEOUT_SECONDS = 20
DEBUG_API_RESPONSE = True
SEARCH_URL = "https://cttrainsapi.confirmtkt.com/api/v1/trains/search"
CLASS_OPTIONS = ["All classes", "SL", "3A", "3E", "2A", "1A", "CC", "EC", "2S"]
DEPARTURE_PERIODS = {
    "All": None,
    "Morning": (360, 720),
    "Afternoon": (720, 1020),
    "Evening": (1020, 1260),
    "Night": (1260, 360),
}
QUOTA_OPTIONS = {
    "General (GN)": "GN",
    "Tatkal (TQ)": "TQ",
    "Premium Tatkal (PT)": "PT",
}


def _station_code(label: str, station_value: Any) -> str:
    """Extract a station code from common station dataset formats."""
    if isinstance(station_value, dict):
        for key in ("code", "station_code", "stationCode", "stn_code", "station"):
            value = station_value.get(key)
            if value and str(value).strip():
                return str(value).strip().upper()
    if "(" in label and ")" in label:
        candidate = label.rsplit("(", 1)[-1].split(")", 1)[0].strip()
        if candidate and candidate.replace(" ", "").isalnum() and len(candidate) <= 6:
            return candidate.upper()
    if isinstance(station_value, str):
        value = station_value.strip()
        if value.isalpha() and len(value) <= 6:
            return value.upper()
    return ""


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.confirmtkt.com",
        "Referer": "https://www.confirmtkt.com/",
        "ClientId": "ct-web",
        "ApiKey": "ct-web!2$",
        "ct-token": "ct-userkey",
        "DeviceId": str(uuid.uuid4()),
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    }


def _debug_response(response: requests.Response) -> None:
    """Print API diagnostics to the terminal, not to the public page."""
    if not DEBUG_API_RESPONSE:
        return
    print("\n========== RAILCONNECT LIVE AVAILABILITY ==========")
    print("Request URL:", response.url)
    print("HTTP status:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type", "unknown"))
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False, default=str))
    except ValueError:
        print(response.text[:10000])
    print("========== END RESPONSE ============================\n")


def _find_train_list(result: dict[str, Any]) -> list[dict[str, Any]] | None:
    containers: list[Any] = [
        result, result.get("data"), result.get("result"), result.get("response")
    ]
    for item in list(containers):
        if isinstance(item, dict):
            containers.extend([
                item.get("data"), item.get("result"), item.get("response")
            ])
    keys = ("trains", "trainList", "train_list", "results", "items", "content")
    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in keys:
            value = container.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                for nested_key in keys:
                    nested = value.get(nested_key)
                    if isinstance(nested, list):
                        return [x for x in nested if isinstance(x, dict)]
    if isinstance(result.get("data"), list):
        return [x for x in result["data"] if isinstance(x, dict)]
    return None


def _find_calendar(result: dict[str, Any]) -> list[dict[str, Any]]:
    for container in (result, result.get("data"), result.get("result")):
        if isinstance(container, dict):
            values = container.get("availability")
            if isinstance(values, list) and any(
                isinstance(x, dict) and "date" in x and "state" in x for x in values
            ):
                return [x for x in values if isinstance(x, dict)]
    return []


def _call_live_availability(
    src_code: str,
    dst_code: str,
    journey_date: date,
    travel_class: str,
    quota: str,
) -> dict[str, Any]:
    """Fetch route results from the observed train-search endpoint."""
    if not src_code or not dst_code:
        raise RuntimeError(
            "Station codes could not be identified. Use station labels such as 'Jaipur Jn (JP)'."
        )
    params = {
        "sourceStationCode": src_code,
        "destinationStationCode": dst_code,
        "addAvailabilityCache": "true",
        "excludeMultiTicketAlternates": "false",
        "excludeBoostAlternates": "false",
        "sortBy": "DEFAULT",
        "dateOfJourney": journey_date.strftime("%d-%m-%Y"),
        "enableNearby": "true",
        "enableTG": "true",
        "tGPlan": "CTG-AW8",
        "showTGPrediction": "false",
        "tgColor": "DEFAULT",
        "showPredictionGlobal": "true",
        "showNewAlternates": "false",
        "showNewAltText": "true",
    }
    try:
        response = requests.get(
            SEARCH_URL, params=params, headers=_headers(), timeout=TIMEOUT_SECONDS
        )
        _debug_response(response)
        if response.status_code in (401, 403, 405, 429):
            raise RuntimeError(
                f"The live availability service rejected the request (HTTP {response.status_code}). "
                "Please try again later."
            )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise RuntimeError("The live availability service took too long to respond.") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not retrieve live train availability: {exc}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("The live availability service returned an unreadable response.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("The live availability service returned an unexpected response format.")
    return {
        "trains": _find_train_list(payload),
        "calendar": _find_calendar(payload),
        "raw": payload,
        "class_requested": travel_class,
        "quota_requested": quota,
        "fetched_at": datetime.now().strftime("%d %b %Y, %I:%M:%S %p"),
    }


def _first(item: dict[str, Any], *keys: str, default: Any = "—") -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _status_raw(value: Any) -> str:
    if isinstance(value, dict):
        value = _first(
            value,
            "currentStatus", "current_status", "bookingStatus", "booking_status",
            "availability", "availablityStatus", "availabilityStatus",
            "status", "state", "text", "title", "message",
            default="",
        )
    return re.sub(r"[\s_-]+", "", str(value or "").upper())


def _status_label(value: Any) -> str:
    if isinstance(value, dict):
        value = _first(
            value, "currentStatus", "current_status", "bookingStatus",
            "booking_status", "availability", "status", "state", "text",
            "title", "message", default="Status not supplied",
        )
    text = str(value) if value not in (None, "") else "Status not supplied"
    upper = text.upper()
    compact = re.sub(r"[\s_-]+", "", upper)

    if "NOTAVAILABLE" in compact or "CANCELLED" in compact:
        return "Not available"
    if any(code in compact for code in ("PQWL", "RLGN", "RSWL", "RQWL", "TQWL")):
        return text
    if "GNWL" in compact or "RLWL" in compact:
        return text
    if compact.startswith("AVAILABLE") or compact.startswith("AVL"):
        return "Available"
    if "FEWSEATS" in compact:
        return "Few seats"
    if "FILLINGFAST" in compact:
        return "Filling fast"
    if "RAC" in compact:
        return "RAC"
    if "WAITLIST" in compact or compact.startswith("WL"):
        return "Waitlist"
    return text


def _status_class(value: Any) -> str:
    """Map railway availability codes to the requested colors."""
    raw = _status_raw(value)

    # Check negative states before AVAILABLE to avoid NOT AVAILABLE turning green.
    if (
        "NOTAVAILABLE" in raw
        or "CANCELLED" in raw
        or any(code in raw for code in ("PQWL", "RLGN", "RSWL", "RQWL", "TQWL"))
    ):
        return "waitlist-red"

    if any(code in raw for code in ("GNWL", "RLWL")):
        return "waitlist-yellow"

    if (
        "RAC" in raw
        or "WAITLIST" in raw
        or raw.startswith("WL")
        or "FEWSEATS" in raw
        or "FILLINGFAST" in raw
    ):
        return "waitlist-yellow"

    if "AVAILABLE" in raw or raw.startswith("AVL"):
        return "available"

    return "neutral"


def _parse_time_minutes(value: Any) -> int | None:
    """Parse common 24-hour or AM/PM departure time formats."""
    if value in (None, "", "—"):
        return None
    match = re.search(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)?", str(value).strip(), re.I)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    meridiem = (match.group(3) or "").upper()
    if minute > 59:
        return None
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour = (0 if hour == 12 else hour) if meridiem == "AM" else (12 if hour == 12 else hour + 12)
    elif hour > 23:
        return None
    return hour * 60 + minute


def _matches_departure_period(departure: Any, period: str) -> bool:
    if period == "All":
        return True
    minutes = _parse_time_minutes(departure)
    if minutes is None:
        return False
    bounds = DEPARTURE_PERIODS.get(period)
    if bounds is None:
        return True
    start, end = bounds
    return (minutes >= start or minutes < end) if start > end else (start <= minutes < end)


def _station_display(label: str) -> tuple[str, str]:
    cleaned = str(label).strip()
    if "(" in cleaned and ")" in cleaned:
        left, remainder = cleaned.rsplit("(", 1)
        code = remainder.split(")", 1)[0].strip()
        if code:
            return left.strip(), code
    return cleaned, ""


def _display_value(value: Any, fallback: str = "—") -> str:
    if value in (None, "", "—"):
        return fallback
    return str(value)


def _render_train_route(
    source_label: str,
    destination_label: str,
    duration: str,
    train_name: str,
    train_number: str,
    departure: str,
    arrival: str,
    departure_date: str,
    arrival_date: str,
) -> None:
    source_name, source_code = _station_display(source_label)
    destination_name, destination_code = _station_display(destination_label)
    source_station = escape(source_name)
    if source_code:
        source_station += f' <span class="journey-station-code">({escape(source_code)})</span>'
    destination_station = escape(destination_name)
    if destination_code:
        destination_station += f' <span class="journey-station-code">({escape(destination_code)})</span>'

    departure_date_html = (
        f'<div class="journey-date-value">{escape(departure_date)}</div>'
        if departure_date and departure_date != "Date not supplied" else ""
    )
    arrival_date_html = (
        f'<div class="journey-date-value">{escape(arrival_date)}</div>'
        if arrival_date and arrival_date != "Date not supplied" else ""
    )

    st.markdown(
        f"""
        <div class="journey-route">
          <div class="journey-train-heading">
            <strong class="journey-train-name">{escape(train_name)}</strong>
            <span class="journey-train-number">{escape(train_number)}</span>
          </div>
          <div class="journey-stations-row">
            <div class="journey-station">
              <div class="journey-time-value">{escape(departure)}</div>
              {departure_date_html}
              <div class="journey-station-name">{source_station}</div>
            </div>
            <div class="journey-track">
              <div class="journey-track-caption">{escape(duration)}</div>
              <div class="journey-track-line">
                <span class="journey-track-dot"></span>
                <span class="journey-track-rail"></span>
                <span class="journey-track-rail"></span>
                <span class="journey-track-dot"></span>
              </div>
            </div>
            <div class="journey-station destination">
              <div class="journey-time-value">{escape(arrival)}</div>
              {arrival_date_html}
              <div class="journey-station-name">{destination_station}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _inject_availability_styles() -> None:
    st.markdown(
        """
        <style>
        .availability-hero {
            padding: 26px 28px; border-radius: 22px; margin: 4px 0 20px;
            background: linear-gradient(120deg,#10234b 0%,#174d78 62%,#168a83 100%);
            color: white; box-shadow: 0 12px 32px rgba(16,35,75,.16);
        }
        .availability-eyebrow { font-size: 11px; letter-spacing: 2px; font-weight: 800;
            text-transform: uppercase; color: #b9eee4; margin-bottom: 8px; }
        .availability-title { font-size: clamp(25px,3vw,34px); line-height: 1.15;
            font-weight: 850; margin-bottom: 8px; color: white; }
        .availability-description { font-size: 14px; line-height: 1.55;
            max-width: 720px; color: #e1f1f7; }
        .availability-train-card {
            background: var(--secondary-background-color,#fff);
            border: 1px solid rgba(110,130,160,.25); border-radius: 18px;
            padding: 18px 20px; margin: 14px 0 8px;
            box-shadow: 0 5px 18px rgba(24,60,106,.06);
        }
        .availability-status {
            display: inline-block; padding: 7px 10px; border-radius: 10px;
            font-size: 12px; font-weight: 800; margin: 4px 0;
            border: 1px solid transparent;
        }
        .availability-status.available { color:#187344; background:#eaf8ef; border-color:#b8e3c7; }
        .availability-status.limited, .availability-status.waitlist-yellow { color:#805500; background:#fff2b3; border-color:#e5c84c; }
        .availability-status.unavailable, .availability-status.waitlist-red { color:#b42318; background:#ffe1df; border-color:#f2a6a1; }
        .availability-status.neutral { color:#4b5870; background:#f1f4f8; border-color:#dbe2eb; }
        .availability-class-card { padding: 10px; border-radius: 13px;
            border: 1px solid rgba(110,130,160,.25); margin: 4px 0;
            min-width: 112px; overflow-wrap: anywhere; height: 100%; }
        .availability-coach-box { border: 1px solid rgba(110,130,160,.28);
            border-radius: 14px; padding: 10px 12px; margin: 12px 0; }
        .availability-coach-scroll { overflow-x: auto; width: 100%; padding-bottom: 4px; }
        .availability-coach-row { display: flex; align-items: stretch; gap: 10px; width: max-content; min-width: 100%; }
        .availability-coach-item { width: 145px; flex: 0 0 145px; }
        .journey-route { padding:16px; margin:12px 0 16px; border-radius:15px;
            border:1px solid rgba(110,130,160,.25); background:var(--secondary-background-color,#fff); }
        .journey-train-heading { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:18px; }
        .journey-train-name { font-size:17px; font-weight:850; }
        .journey-train-number { font-size:16px; font-weight:800; color:#168a83; }
        .journey-stations-row { display:grid; grid-template-columns:minmax(0,1fr) minmax(100px,1.15fr) minmax(0,1fr); align-items:center; gap:12px; }
        .journey-time-value { font-size:20px; font-weight:850; }
        .journey-date-value { font-size:11px; opacity:.72; margin:2px 0 8px; }
        .journey-station-name { font-size:15px; font-weight:850; overflow-wrap:anywhere; }
        .journey-station-code { font-size:12px; opacity:.65; font-weight:600; }
        .journey-station.destination { text-align:right; }
        .journey-track { display:flex; flex-direction:column; align-items:center; min-width:0; }
        .journey-track-caption { font-size:12px; font-weight:850; color:#168a83; margin-bottom:8px; }
        .journey-track-line { display:flex; align-items:center; width:100%; gap:0; }
        .journey-track-dot { width:10px; height:10px; border:3px solid #168a83; border-radius:50%; flex-shrink:0; }
        .journey-track-rail { height:3px; background:linear-gradient(90deg,#168a83,#3b82f6); flex:1; }
        .availability-class-code { font-weight:850; font-size:14px; margin-bottom:5px; }
        .availability-fare { font-weight:800; font-size:14px; margin-top:7px; }
        .availability-section-heading { font-size:20px; font-weight:850; margin:8px 0 2px; }
        @media(max-width:600px) {
            .journey-stations-row { grid-template-columns:minmax(0,1fr); gap:14px; }
            .journey-station.destination { text-align:left; }
            .journey-track { align-items:flex-start; }
            .journey-track-line { max-width:220px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _departure_value(train: dict[str, Any]) -> Any:
    return _first(train, "departureTime", "departure", "fromTime", "depTime")


def _render_live_results(
    result: dict[str, Any],
    travel_class: str,
    source_label: str,
    destination_label: str,
    departure_period: str = "All",
) -> None:
    calendar = result.get("calendar") or []
    trains = result.get("trains")

    if calendar:
        st.markdown(
            '<div class="availability-section-heading">Date availability overview</div>',
            unsafe_allow_html=True,
        )
        st.caption("These are general date-level indicators, not exact seat counts.")
        visible_calendar = calendar[:7]
        columns = st.columns(len(visible_calendar))
        for i, item in enumerate(visible_calendar):
            status = item.get("state", "Unknown")
            with columns[i]:
                st.markdown(f"**{escape(str(item.get('date', 'Date unknown')))}**")
                st.markdown(
                    f'<span class="availability-status {_status_class(status)}">'
                    f'{escape(_status_label(status))}</span>',
                    unsafe_allow_html=True,
                )

    if trains is None:
        st.info(
            "The service responded, but its response did not include a recognizable train list. "
            "Date-level indicators, if shown, do not identify individual trains."
        )
        st.caption("Technical response details are available in the terminal running RailConnect.")
        return
    if not trains:
        st.info("No train results were returned for this route and date.")
        return

    filtered_trains = [
        train for train in trains
        if _matches_departure_period(_departure_value(train), departure_period)
    ]
    filtered_trains.sort(
        key=lambda train: (
            _parse_time_minutes(_departure_value(train)) is None,
            _parse_time_minutes(_departure_value(train))
            if _parse_time_minutes(_departure_value(train)) is not None
            else 24 * 60,
        )
    )

    st.markdown(
        '<div class="availability-section-heading">Live train results</div>',
        unsafe_allow_html=True,
    )
    if departure_period == "All":
        st.caption(f"{len(trains)} trains found. Live results may change.")
    else:
        st.caption(
            f"{len(filtered_trains)} of {len(trains)} trains match the "
            f"{departure_period.lower()} departure filter."
        )
    if not filtered_trains:
        st.info(
            f"No trains match the {departure_period.lower()} filter. "
            "Try another period or select All."
        )
        return

    for train in filtered_trains:
        name = _display_value(_first(train, "trainName", "name", "train_name", default="Train"), "Train")
        number = _display_value(_first(train, "trainNumber", "trainNo", "number", "train_number"))
        departure = _display_value(_departure_value(train))
        arrival = _display_value(_first(train, "arrivalTime", "arrival", "toTime", "arrTime"))
        departure_date = _display_value(
            _first(train, "departureDate", "departDate", "fromDate", "journeyDate", default="Date not supplied"),
            "Date not supplied",
        )
        arrival_date = _display_value(
            _first(train, "arrivalDate", "arriveDate", "toDate", default="Date not supplied"),
            "Date not supplied",
        )
        duration_value = _first(train, "duration", "journeyDuration", "travelTime")
        try:
            if isinstance(duration_value, (int, float)) or str(duration_value).isdigit():
                minutes = int(duration_value)
                duration = f"{minutes // 60}h {minutes % 60:02d}m"
            else:
                duration = str(duration_value)
        except (TypeError, ValueError):
            duration = str(duration_value)

        _render_train_route(
            source_label, destination_label, duration, name, number,
            departure, arrival, departure_date, arrival_date,
        )
        st.link_button(
            "Book on IRCTC",
            "https://www.irctc.co.in/nget/train-search",
            use_container_width=False,
        )

        availability = (
            train.get("availabilityCache")
            or train.get("availability")
            or train.get("classes")
        )
        if isinstance(availability, dict):
            codes = list(availability) if travel_class == "All classes" else [travel_class]
            rendered = []
            for class_code in codes:
                details = availability.get(class_code)
                if details is None:
                    continue
                status = (
                    _first(
                        details,
                        "currentStatus", "current_status", "bookingStatus",
                        "booking_status", "availability", "status",
                        "availablityStatus", "availabilityStatus", "state",
                        "text", "title", "message",
                        default="Status not supplied",
                    )
                    if isinstance(details, dict) else details
                )
                fare = (
                    _first(details, "fare", "totalFare", "amount", default=None)
                    if isinstance(details, dict) else None
                )
                rendered.append((class_code, status, fare))

            if rendered:
                with st.container(border=True):
                    st.markdown("**Coach availability**")
                    coach_html = []
                    for class_code, status, fare in rendered:
                        fare_html = (
                            f'<div class="availability-fare">₹{escape(str(fare))}</div>'
                            if fare is not None else ""
                        )
                        coach_html.append(
                            '<div class="availability-coach-item">'
                            '<div class="availability-class-card">'
                            f'<div class="availability-class-code">{escape(str(class_code))}</div>'
                            f'<span class="availability-status {_status_class(status)}">'
                            f'{escape(_status_label(status))}</span>'
                            f'{fare_html}</div></div>'
                        )
                    st.markdown(
                        '<div class="availability-coach-scroll"><div class="availability-coach-row">'
                        + "".join(coach_html)
                        + "</div></div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No class-specific availability was included for the selected class.")


def _fetch_for_query(query: dict[str, Any]) -> dict[str, Any]:
    return _call_live_availability(
        query.get("src_code", ""),
        query.get("dst_code", ""),
        query.get("journey_date", date.today()),
        query.get("travel_class", "All classes"),
        QUOTA_OPTIONS.get(query.get("quota", "General (GN)"), "GN"),
    )


def render_train_availability(
    *, stations, data, find_journeys, deduplicate_journeys, safe, render_journey
):
    """Render train availability without changing other RailConnect modules."""
    _inject_availability_styles()
    st.markdown(
        """
        <div class="availability-hero">
            <div class="availability-eyebrow">RailConnect · Journey tools</div>
            <div class="availability-title">Find your train</div>
            <div class="availability-description">
                Compare trains, check class-wise availability and refresh results
                whenever you need the latest response.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    station_labels = list(stations.keys())
    with st.container(border=True):
        st.markdown("### Search your journey")
        st.caption("Choose your stations, travel date, class and quota.")
        from_col, swap_col, to_col = st.columns([5, 0.8, 5], vertical_alignment="bottom")
        with from_col:
            source_label = st.selectbox(
                "From station",
                station_labels,
                index=None,
                placeholder="Select departure station",
                key="availability_source_station",
            )
        with swap_col:
            def swap_stations():
                source = st.session_state.get("availability_source_station")
                destination = st.session_state.get("availability_destination_station")
                st.session_state.availability_source_station = destination
                st.session_state.availability_destination_station = source

            st.button(
                "⇄",
                key="availability_swap_stations",
                help="Reverse from and to stations",
                on_click=swap_stations,
                use_container_width=True,
            )
        with to_col:
            destination_label = st.selectbox(
                "To station",
                station_labels,
                index=None,
                placeholder="Select destination station",
                key="availability_destination_station",
            )

        date_col, class_col, quota_col = st.columns(3)
        with date_col:
            journey_date = st.date_input(
                "Journey date",
                value=date.today(),
                min_value=date.today(),
                format="DD/MM/YYYY",
                key="availability_journey_date",
            )
        with class_col:
            travel_class = st.selectbox(
                "Travel class", CLASS_OPTIONS, key="availability_travel_class"
            )
        with quota_col:
            quota_label = st.selectbox(
                "Quota", list(QUOTA_OPTIONS), key="availability_quota"
            )

        filter_col, _ = st.columns([1, 2])
        with filter_col:
            departure_period = st.selectbox(
                "Filter by departure time",
                options=list(DEPARTURE_PERIODS.keys()),
                format_func=lambda period: {
                    "All": "All times",
                    "Morning": "Morning: 06:00–11:59",
                    "Afternoon": "Afternoon: 12:00–16:59",
                    "Evening": "Evening: 17:00–20:59",
                    "Night": "Night: 21:00–05:59",
                }.get(period, period),
                key="availability_departure_period",
            )

        clicked = st.button(
            "Search trains",
            type="primary",
            use_container_width=True,
            key="availability_search_button",
        )

    if clicked:
        if not source_label or not destination_label:
            st.warning("Please select both departure and destination stations.")
        elif stations[source_label] == stations[destination_label]:
            st.warning("Choose two different stations.")
        else:
            query = {
                "source_label": source_label,
                "destination_label": destination_label,
                "journey_date": journey_date,
                "travel_class": travel_class,
                "quota": quota_label,
                "departure_period": departure_period,
                "src_code": _station_code(source_label, stations[source_label]),
                "dst_code": _station_code(destination_label, stations[destination_label]),
            }
            st.session_state.availability_query = query
            st.session_state.availability_status = "loading"
            st.session_state.availability_error = None
            try:
                with st.spinner("Searching live train availability..."):
                    live_result = _fetch_for_query(query)
                    local = find_journeys(
                        data=data,
                        source=stations[source_label],
                        destination=stations[destination_label],
                        journey_date=journey_date,
                        max_changes=0,
                        min_transfer=30,
                        departure_period="All",
                    )
                    st.session_state.availability_live_results = live_result
                    st.session_state.availability_results = deduplicate_journeys(local)
                    st.session_state.availability_status = "complete"
            except Exception as exc:
                st.session_state.availability_error = str(exc)
                st.session_state.availability_live_results = None
                st.session_state.availability_status = "error"

    status = st.session_state.get("availability_status")
    if status not in ("complete", "error"):
        return
    query = st.session_state.get("availability_query", {})
    if not query:
        return

    source = safe(query.get("source_label", ""))
    destination = safe(query.get("destination_label", ""))
    journey = query.get("journey_date", date.today())
    st.markdown(
        '<div class="availability-section-heading">Your results</div>'
        f'<div style="opacity:.75;margin-bottom:10px">{source} → {destination}'
        f' &nbsp;·&nbsp; {journey:%d %b %Y}</div>',
        unsafe_allow_html=True,
    )

    refresh_col, info_col = st.columns([1, 2], vertical_alignment="center")
    with refresh_col:
        refresh_clicked = st.button(
            "Refresh availability",
            use_container_width=True,
            key="availability_refresh_button",
        )
    with info_col:
        fetched = (st.session_state.get("availability_live_results") or {}).get("fetched_at")
        if fetched:
            st.caption(f"Last checked: {fetched}")
        else:
            st.caption("Refresh to retry the live availability request.")

    if refresh_clicked:
        try:
            with st.spinner("Refreshing live availability..."):
                st.session_state.availability_live_results = _fetch_for_query(query)
                st.session_state.availability_error = None
                st.session_state.availability_status = "complete"
        except Exception as exc:
            st.session_state.availability_error = str(exc)
            st.session_state.availability_live_results = None
            st.session_state.availability_status = "error"
        st.rerun()

    if status == "error":
        st.error(
            "Live availability could not be loaded: "
            + st.session_state.get("availability_error", "Unknown error")
        )

    live_result = st.session_state.get("availability_live_results")
    if live_result is not None and status != "error":
        _render_live_results(
            live_result,
            query.get("travel_class", "All classes"),
            query.get("source_label", ""),
            query.get("destination_label", ""),
            st.session_state.get(
                "availability_departure_period",
                query.get("departure_period", "All"),
            ),
        )
    elif status == "error":
        st.info("Your search details are saved. Use Refresh availability to try again.")

    local = st.session_state.get("availability_results") or []
    if local:
        with st.expander("Local timetable matches"):
            st.caption(
                "These are schedule records only; they do not confirm current seats or fares."
            )
            for number, item in enumerate(local, start=1):
                render_journey(item, number, journey)
