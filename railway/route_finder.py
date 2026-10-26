#Route_Finder.py
from bisect import bisect_left
from datetime import date, datetime, timedelta
import re

SEARCH_DAYS = 8
RESULTS_PER_LEVEL = 10
TRANSFER_FALLBACKS = (30, 20, 15, 10, 0)

DEPARTURE_PERIODS = {
    "All": (0, 1439),
    "Morning": (360, 719),
    "Afternoon": (720, 1019),
    "Evening": (1020, 1259),
    "Night": (1260, 359),
}

SLOT_ORDER = ("Morning", "Afternoon", "Evening", "Night")

SLOT_RANGES = {
    "Morning": (360, 719),
    "Afternoon": (720, 1019),
    "Evening": (1020, 1259),
    "Night": (1260, 359),
}

_INDEX_CACHE = {}


def _parse_time(value):
    if value is None:
        return None

    text = str(value).strip()

    if not text or text.lower() in {
        "nan", "none", "null", "-", "--"
    }:
        return None

    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", text)

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if hour > 23 or minute > 59:
        return None

    return hour * 60 + minute


def _as_float(value):
    try:
        text = str(value).strip()

        if not text or text.lower() in {
            "nan", "none", "null", "-"
        }:
            return None

        return float(text.replace(",", ""))

    except (TypeError, ValueError):
        return None


def _first_value(record, *keys, default=None):
    if not isinstance(record, dict):
        return default

    for key in keys:
        value = record.get(key)

        if value is not None and str(value).strip().lower() not in {
            "", "nan", "none", "null"
        }:
            return value

    return default


def _running_on(train, service_date):
    value = _first_value(
        train,
        "runningDays",
        "running_days",
        "runs_days",
        "runsDays",
        "daysOfRun",
        "days_of_run",
        default="",
    )

    text = str(value).strip().lower()

    if not text or text in {
        "daily", "everyday", "every day", "all days"
    }:
        return True

    compact = re.sub(r"[\s,/-]", "", text)

    if len(compact) == 7 and set(compact) <= {"0", "1"}:
        return compact[service_date.weekday()] == "1"

    weekdays = {
        "mon": 0, "monday": 0,
        "tue": 1, "tues": 1, "tuesday": 1,
        "wed": 2, "wednesday": 2,
        "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
        "fri": 4, "friday": 4,
        "sat": 5, "saturday": 5,
        "sun": 6, "sunday": 6,
    }

    tokens = re.findall(r"[a-z]+", text)
    selected = set()

    for token in tokens:
        if token in {"daily", "everyday"}:
            return True

        if token in weekdays:
            selected.add(weekdays[token])
        elif token[:3] in weekdays:
            selected.add(weekdays[token[:3]])

    return service_date.weekday() in selected if selected else True


def _normalise_stops(train):
    """
    Normalize a train's route into monotonically increasing minutes.

    Explicit journey-day values are respected. When journey-day values are
    missing/defaulted, clock rollover is inferred as before, with an
    additional distance/time sanity check for routes whose cumulative
    distance proves that a clock-only duration is impossible.

    Distance is only used to detect impossible short durations; it does not
    assume that every long-distance leg necessarily takes an extra day.
    """
    raw_stops = (
        train.get("completeOrderedRoute")
        or train.get("stops")
        or train.get("route")
        or []
    )

    if not isinstance(raw_stops, list):
        return []

    parsed = []
    inferred_day_offset = 0
    previous_time = None

    for index, raw in enumerate(raw_stops):
        if not isinstance(raw, dict):
            continue

        code = str(_first_value(
            raw,
            "stationCode",
            "station_code",
            "code",
            default="",
        )).strip().upper()

        if not code:
            continue

        name = str(_first_value(
            raw,
            "stationName",
            "station_name",
            "name",
            default=code,
        )).strip()

        arrival_clock = _parse_time(_first_value(
            raw,
            "arrivalTime",
            "arrival_time",
            "arrival",
        ))

        departure_clock = _parse_time(_first_value(
            raw,
            "departureTime",
            "departure_time",
            "departure",
        ))

        raw_day = _first_value(
            raw,
            "journeyDay",
            "journey_day",
            "day",
            "dayNumber",
            "day_number",
            default=None,
        )

        try:
            day_number = max(1, int(float(raw_day))) if raw_day is not None else None
        except (TypeError, ValueError):
            day_number = None

        distance = _as_float(_first_value(
            raw,
            "distance",
            "distanceKm",
            "distance_km",
            "distanceFromSource",
            "distance_from_source",
        ))

        clocks = [
            t for t in (arrival_clock, departure_clock)
            if t is not None
        ]

        if day_number is not None and day_number > 1:
            offset = (day_number - 1) * 1440
            inferred_day_offset = max(inferred_day_offset, offset)
        else:
            # Infer an overnight rollover when the next station's clock
            # moves substantially backwards.
            if (
                clocks
                and previous_time is not None
                and min(clocks) + inferred_day_offset < previous_time - 720
            ):
                inferred_day_offset += 1440

            offset = inferred_day_offset

        arrival = arrival_clock + offset if arrival_clock is not None else None
        departure = departure_clock + offset if departure_clock is not None else None

        valid_times = [t for t in (arrival, departure) if t is not None]
        if valid_times:
            previous_time = max(valid_times)

        parsed.append({
            "code": code,
            "name": name,
            "arrival": arrival,
            "departure": departure,
            "distance": distance,
            "sequence": index,
            "_arrival_clock": arrival_clock,
            "_departure_clock": departure_clock,
            "_explicit_day": day_number,
        })

    # Some data sources omit journeyDay on later stops. Detect a clearly
    # impossible elapsed time from the first stop using cumulative route
    # distance. A generous maximum plausible average speed (140 km/h)
    # avoids altering ordinary same-day legs. If a stop is too early, move
    # it forward by whole days, and keep subsequent inferred stops aligned.
    first_timed = next(
        (
            stop for stop in parsed
            if stop["departure"] is not None or stop["arrival"] is not None
        ),
        None,
    )

    if first_timed is not None and first_timed["distance"] is not None:
        first_time = (
            first_timed["departure"]
            if first_timed["departure"] is not None
            else first_timed["arrival"]
        )
        first_distance = first_timed["distance"]
        rolling_extra = 0

        for stop in parsed:
            if stop is first_timed:
                continue

            # Explicit day information wins; do not override it using a
            # heuristic. Distance sanity check is for missing/default day.
            if stop["_explicit_day"] is not None and stop["_explicit_day"] > 1:
                continue

            stop_time = (
                stop["arrival"]
                if stop["arrival"] is not None
                else stop["departure"]
            )
            if stop_time is None or stop["distance"] is None:
                continue

            distance_delta = stop["distance"] - first_distance
            if distance_delta <= 0:
                continue

            elapsed = stop_time + rolling_extra - first_time
            minimum_plausible_minutes = (distance_delta / 140.0) * 60.0

            while elapsed < minimum_plausible_minutes:
                rolling_extra += 1440
                elapsed += 1440

            if rolling_extra:
                if stop["arrival"] is not None:
                    stop["arrival"] += rolling_extra
                if stop["departure"] is not None:
                    stop["departure"] += rolling_extra

    # Strip internal parsing fields before returning records.
    stops = []
    previous_normalized_time = None

    for stop in parsed:
        normalized = {
            key: value
            for key, value in stop.items()
            if not key.startswith("_")
        }

        valid_times = [
            t for t in (normalized["arrival"], normalized["departure"])
            if t is not None
        ]
        if valid_times:
            previous_normalized_time = max(valid_times)

        stops.append(normalized)

    return stops


def _dataset_signature(data):
    trains = data.get("trains", [])

    return (
        id(data),
        len(trains),
        sum(
            len(
                train.get("completeOrderedRoute")
                or train.get("stops")
                or train.get("route")
                or []
            )
            for train in trains
        ),
    )


def _build_graph(by_station):
    graph = {}

    for source, entries in by_station.items():
        destinations = graph.setdefault(source, set())

        for service, start_index in entries:
            for stop in service["stops"][start_index + 1:]:
                if stop["arrival"] is not None:
                    destinations.add(stop["code"])

    reverse_graph = {}

    for source, destinations in graph.items():
        for target in destinations:
            reverse_graph.setdefault(target, set()).add(source)

    return graph, reverse_graph


def _build_index(data, journey_date):
    by_station = {}
    station_names = {}

    for train in data.get("trains", []):
        stops = _normalise_stops(train)

        if len(stops) < 2:
            continue

        number = str(_first_value(
            train,
            "trainNumber",
            "train_number",
            "number",
            default="",
        )).strip()

        if not number:
            continue

        name = str(_first_value(
            train,
            "trainName",
            "train_name",
            "name",
            default="Unknown train",
        )).strip()

        for stop in stops:
            station_names[stop["code"]] = stop["name"]

        for offset in range(SEARCH_DAYS):
            service_date = journey_date + timedelta(days=offset)

            if not _running_on(train, service_date):
                continue

            shift = offset * 1440

            shifted_stops = [
                {
                    **stop,
                    "arrival": (
                        stop["arrival"] + shift
                        if stop["arrival"] is not None
                        else None
                    ),
                    "departure": (
                        stop["departure"] + shift
                        if stop["departure"] is not None
                        else None
                    ),
                }
                for stop in stops
            ]

            service = {
                "number": number,
                "name": name,
                "service_date": service_date,
                "stops": shifted_stops,
            }

            for stop_index, stop in enumerate(shifted_stops):
                if stop["departure"] is not None:
                    by_station.setdefault(
                        stop["code"], []
                    ).append((service, stop_index))

    departure_times = {}

    for station, entries in by_station.items():
        entries.sort(key=lambda entry: (
            entry[0]["stops"][entry[1]]["departure"],
            entry[0]["number"],
            entry[0]["service_date"],
        ))

        departure_times[station] = [
            service["stops"][index]["departure"]
            for service, index in entries
        ]

    graph, reverse_graph = _build_graph(by_station)

    return {
        "by_station": by_station,
        "departure_times": departure_times,
        "station_names": station_names,
        "graph": graph,
        "reverse_graph": reverse_graph,
        "reachability": {},
    }


def _get_index(data, journey_date):
    key = (_dataset_signature(data), journey_date.isoformat())

    if key not in _INDEX_CACHE:
        _INDEX_CACHE.clear()
        _INDEX_CACHE[key] = _build_index(data, journey_date)

    return _INDEX_CACHE[key]


def _distance_between(start, end):
    start_distance = start.get("distance")
    end_distance = end.get("distance")

    if start_distance is None or end_distance is None:
        return None

    difference = end_distance - start_distance

    return difference if difference >= 0 else None


def _make_leg(service, start_index, end_index):
    stops = service["stops"]
    start = stops[start_index]
    end = stops[end_index]

    if start["departure"] is None or end["arrival"] is None:
        return None

    if end["arrival"] <= start["departure"]:
        return None

    return {
        "number": service["number"],
        "name": service["name"],
        "source": start["code"],
        "source_name": start["name"],
        "destination": end["code"],
        "destination_name": end["name"],
        "departure": start["departure"],
        "arrival": end["arrival"],
        "duration": end["arrival"] - start["departure"],
        "distance_km": _distance_between(start, end),
        "service_date": service["service_date"],
    }


def _departure_matches(departure, departure_period):
    if departure_period == "All":
        return True

    if departure_period not in DEPARTURE_PERIODS:
        raise ValueError(
            f"Unknown departure period: {departure_period!r}"
        )

    start, end = DEPARTURE_PERIODS[departure_period]
    clock_minutes = departure % 1440

    if start <= end:
        return start <= clock_minutes <= end

    return clock_minutes >= start or clock_minutes <= end


def _slot_for_time(minutes):
    clock = minutes % 1440

    if 360 <= clock <= 719:
        return "Morning"
    if 720 <= clock <= 1019:
        return "Afternoon"
    if 1020 <= clock <= 1259:
        return "Evening"

    return "Night"


def _slot_bucket(minutes):
    """
    Assign departures to chronological slots.

    Night is considered to start at 21:00. Departures from 00:00
    through 05:59 belong to the Night slot that started the previous
    calendar evening.
    """
    day = minutes // 1440
    clock = minutes % 1440

    if clock < 360:
        return (day - 1) * 4 + 3
    if clock < 720:
        return day * 4
    if clock < 1020:
        return day * 4 + 1
    if clock < 1260:
        return day * 4 + 2

    return day * 4 + 3


def _first_leg_positions(
    entries,
    times,
    start_position,
    journey_date,
    departure_period,
):
    """
    Find first-train departures efficiently.

    The selected period applies to the first train only. For Night,
    early-morning and late-evening departures are both included.
    """
    if departure_period == "All":
        return range(start_position, len(entries))

    if departure_period == "Night":
        windows = ((0, 359), (1260, 1439))
    else:
        windows = (DEPARTURE_PERIODS[departure_period],)

    positions = set()

    for start_clock, end_clock in windows:
        day_start = (
            journey_date - journey_date
        ).days * 1440

        left = bisect_left(
            times,
            day_start + start_clock,
            start_position,
        )
        right = bisect_left(
            times,
            day_start + end_clock + 1,
            left,
        )

        positions.update(range(left, right))

    return sorted(
        position
        for position in positions
        if entries[position][0]["service_date"] == journey_date
    )


def _legs_from_station(
    by_station,
    departure_times,
    station,
    earliest_departure,
    latest_arrival,
    journey_date,
    first_leg,
    departure_period="All",
    useful_destinations=None,
):
    entries = by_station.get(station, [])
    times = departure_times.get(station, [])

    if not entries:
        return []

    start_position = bisect_left(times, earliest_departure)

    if first_leg and departure_period != "All":
        candidate_positions = _first_leg_positions(
            entries,
            times,
            start_position,
            journey_date,
            departure_period,
        )
    else:
        candidate_positions = range(start_position, len(entries))

    options = []

    for position in candidate_positions:
        service, start_index = entries[position]
        start = service["stops"][start_index]
        departure = start["departure"]

        if departure is None:
            continue

        if departure > latest_arrival:
            break

        if first_leg:
            if service["service_date"] != journey_date:
                continue

            if not _departure_matches(departure, departure_period):
                continue

        stops = service["stops"]

        for end_index in range(start_index + 1, len(stops)):
            end = stops[end_index]

            if end["arrival"] is None:
                continue

            if end["arrival"] <= departure:
                continue

            if end["arrival"] > latest_arrival:
                break

            if (
                useful_destinations is not None
                and end["code"] not in useful_destinations
            ):
                continue

            leg = _make_leg(service, start_index, end_index)

            if leg is not None:
                options.append(leg)

    options.sort(key=lambda leg: (
        leg["departure"],
        leg["arrival"],
        leg["duration"],
        leg["distance_km"] is None,
        leg["distance_km"]
        if leg["distance_km"] is not None
        else float("inf"),
        leg["number"],
        leg["destination"],
    ))

    return options


def _summarise_journey(legs):
    departure = legs[0]["departure"]
    arrival = legs[-1]["arrival"]

    transfers = [
        legs[i + 1]["departure"] - legs[i]["arrival"]
        for i in range(len(legs) - 1)
    ]

    distances = [leg["distance_km"] for leg in legs]

    total_distance = (
        sum(distances)
        if distances and all(
            distance is not None for distance in distances
        )
        else None
    )

    return {
        "legs": legs,
        "changes": len(legs) - 1,
        "departure": departure,
        "arrival": arrival,
        "duration": arrival - departure,
        "waiting": sum(transfers),
        "distance_km": total_distance,
        "minimum_transfer_used": (
            min(transfers) if transfers else None
        ),
    }


def _journey_signature(journey):
    """
    Identify an itinerary by its actual train legs and times.

    This removes duplicate results without treating two different
    train combinations as the same journey.
    """
    return tuple(
        (
            leg["number"],
            leg["source"],
            leg["destination"],
            leg["departure"],
            leg["arrival"],
        )
        for leg in journey["legs"]
    )


def _journey_sort_key(journey):
    distance = journey["distance_km"]

    return (
        journey["duration"],
        distance is None,
        distance if distance is not None else float("inf"),
        journey["waiting"],
        journey["departure"],
        _journey_signature(journey),
    )


def _stations_reaching_destination(reverse_graph, destination, max_legs):
    reachable = {destination}
    frontier = {destination}

    for _ in range(max_legs):
        previous = set()

        for station in frontier:
            previous.update(reverse_graph.get(station, ()))

        previous -= reachable

        if not previous:
            break

        reachable.update(previous)
        frontier = previous

    return reachable


def _get_reachable(index, destination, max_legs):
    key = (destination, max_legs)
    cache = index["reachability"]

    if key not in cache:
        cache[key] = _stations_reaching_destination(
            index["reverse_graph"],
            destination,
            max_legs,
        )

    return cache[key]


def _search_exact_changes(
    index,
    source,
    destination,
    journey_date,
    changes,
    min_transfer,
    departure_period="All",
):
    by_station = index["by_station"]
    departure_times = index["departure_times"]

    latest_arrival = SEARCH_DAYS * 1440
    max_legs = changes + 1

    reachable_by_remaining_legs = {
        remaining: _get_reachable(index, destination, remaining)
        for remaining in range(max_legs + 1)
    }

    results = {}

    def walk(station, legs, visited_stations, used_trains):
        legs_used = len(legs)
        remaining_legs = max_legs - legs_used

        if station == destination and legs:
            if legs_used == max_legs:
                journey = _summarise_journey(legs)
                results.setdefault(
                    _journey_signature(journey),
                    journey,
                )
                return True

            return False

        if remaining_legs <= 0:
            return False

        if station not in reachable_by_remaining_legs[remaining_legs]:
            return False

        earliest_departure = (
            0
            if not legs
            else legs[-1]["arrival"] + min_transfer
        )

        useful_destinations = reachable_by_remaining_legs[
            remaining_legs - 1
        ]

        candidates = _legs_from_station(
            by_station=by_station,
            departure_times=departure_times,
            station=station,
            earliest_departure=earliest_departure,
            latest_arrival=latest_arrival,
            journey_date=journey_date,
            first_leg=not legs,
            departure_period=departure_period,
            useful_destinations=useful_destinations,
        )

        candidates = [
            leg for leg in candidates
            if leg["number"] not in used_trains
            and (
                leg["destination"] not in visited_stations
                or leg["destination"] == destination
            )
            and not (
                leg["destination"] == destination
                and remaining_legs > 1
            )
        ]

        if not candidates:
            return False

        if not legs:
            # The user's selected period controls the first train.
            # "All" preserves the ordinary chronological search.
            slot_groups = [(None, candidates)]
        else:
            grouped = {}

            for leg in candidates:
                bucket = _slot_bucket(leg["departure"])
                grouped.setdefault(bucket, []).append(leg)

            slot_groups = [
                (
                    bucket,
                    sorted(group, key=lambda leg: (
                        leg["departure"],
                        leg["arrival"],
                        leg["number"],
                        leg["destination"],
                    )),
                )
                for bucket, group in sorted(grouped.items())
            ]

        found_in_context = False

        for _, slot_candidates in slot_groups:
            found_in_slot = False

            for leg in slot_candidates:
                next_station = leg["destination"]

                found = walk(
                    next_station,
                    legs + [leg],
                    visited_stations | {next_station},
                    used_trains | {leg["number"]},
                )

                if found:
                    found_in_slot = True
                    found_in_context = True

            # For a particular connection point, stop advancing through
            # later slots once this slot can complete the requested
            # number of legs. Two-change routes apply this independently
            # at each transfer point.
            if legs and found_in_slot:
                break

        return found_in_context

    walk(source, [], {source}, set())

    return sorted(results.values(), key=_journey_sort_key)


def find_journeys(
    data,
    source,
    destination,
    journey_date,
    max_changes=2,
    min_transfer=30,
    departure_period="All",
):
    """
    Return direct, one-interchange and two-interchange journeys.

    The selected departure period filters the first train only.
    Connection departures are explored in chronological slot order.

    For each connection, later slots are explored only if the current
    slot cannot complete a journey with the requested number of legs.

    Minimum transfer time is relaxed only if no journeys are found
    for that connection-count category at the stricter threshold.
    """
    if isinstance(journey_date, datetime):
        journey_date = journey_date.date()

    if not isinstance(journey_date, date):
        raise TypeError(
            "journey_date must be a datetime.date value"
        )

    if departure_period not in DEPARTURE_PERIODS:
        raise ValueError(
            f"Unknown departure period: {departure_period!r}. "
            f"Choose one of {', '.join(DEPARTURE_PERIODS)}."
        )

    source = str(source).strip().upper()
    destination = str(destination).strip().upper()

    if source == destination:
        return []

    max_changes = max(0, min(2, int(max_changes)))
    requested_minimum = max(0, int(min_transfer))

    index = _get_index(data, journey_date)
    by_station = index["by_station"]

    if source not in by_station or destination not in by_station:
        return []

    results = []

    direct = _search_exact_changes(
        index=index,
        source=source,
        destination=destination,
        journey_date=journey_date,
        changes=0,
        min_transfer=0,
        departure_period=departure_period,
    )

    direct.sort(key=lambda journey: (
        journey["departure"],
        journey["duration"],
        journey["distance_km"] is None,
        journey["distance_km"]
        if journey["distance_km"] is not None
        else float("inf"),
    ))

    seen_signatures = set()

    for journey in direct:
        signature = _journey_signature(journey)

        if signature in seen_signatures:
            continue

        seen_signatures.add(signature)
        journey["transfer_threshold_used"] = None
        journey["short_transfer_warning"] = False
        results.append(journey)

        if len(seen_signatures) >= RESULTS_PER_LEVEL:
            break

    thresholds = []

    for threshold in (requested_minimum, *TRANSFER_FALLBACKS):
        if threshold not in thresholds:
            thresholds.append(threshold)

    for changes in range(1, max_changes + 1):
        category_routes = []
        threshold_used = requested_minimum

        for threshold in thresholds:
            candidates = _search_exact_changes(
                index=index,
                source=source,
                destination=destination,
                journey_date=journey_date,
                changes=changes,
                min_transfer=threshold,
                departure_period=departure_period,
            )

            if candidates:
                category_routes = candidates
                threshold_used = threshold
                break

        category_routes.sort(key=_journey_sort_key)

        category_seen = set()
        added = 0

        for journey in category_routes:
            signature = _journey_signature(journey)

            if signature in category_seen:
                continue

            category_seen.add(signature)

            journey["transfer_threshold_used"] = threshold_used

            journey["short_transfer_warning"] = any(
                journey["legs"][i + 1]["departure"]
                - journey["legs"][i]["arrival"]
                < requested_minimum
                for i in range(len(journey["legs"]) - 1)
            )

            results.append(journey)
            added += 1

            if added >= RESULTS_PER_LEVEL:
                break

    return results