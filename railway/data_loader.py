#Data_Loader.py
import csv
from collections import defaultdict
from pathlib import Path

import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data" / "raw"

# Exclude special, parcel, and tourist services.
EXCLUDED_TYPES = {"TOD", "PEXP", "TRST"}


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


@st.cache_data(show_spinner="Loading railway CSV schedules...")
def load_data():
    train_rows = read_csv(DATA_DIR / "trains.csv")
    stop_rows = read_csv(DATA_DIR / "stops.csv")
    station_rows = read_csv(DATA_DIR / "stations.csv")

    if not train_rows or not stop_rows:
        raise ValueError("The train or stop CSV file is empty.")

    train_columns = set(train_rows[0])
    stop_columns = set(stop_rows[0])

    required_trains = {
        "number", "name", "type", "type_label", "runs_days"
    }
    required_stops = {
        "train_number", "seq", "station_code", "station_name",
        "day", "arrival", "departure"
    }

    if not required_trains.issubset(train_columns):
        raise ValueError("trains.csv is missing required columns.")

    if not required_stops.issubset(stop_columns):
        raise ValueError("stops.csv is missing required columns.")

    metadata = {}

    for row in train_rows:
        number = str(row.get("number") or "").strip()
        train_type = str(row.get("type") or "").strip().upper()

        if not number or train_type in EXCLUDED_TYPES:
            continue

        metadata[number] = {
            "trainNumber": number,
            "trainName": str(row.get("name") or number).strip(),
            "trainType": train_type,
            "trainTypeLabel": str(row.get("type_label") or "").strip(),
            "runningDays": str(row.get("runs_days") or "").strip(),
        }

    routes = defaultdict(list)
    station_names = {}

    for row in stop_rows:
        number = str(row.get("train_number") or "").strip()

        if number not in metadata:
            continue

        code = str(row.get("station_code") or "").strip()

        if not code:
            continue

        name = str(row.get("station_name") or code).strip()
        station_names.setdefault(code, name)

        try:
            sequence = int(row.get("seq") or 0)
        except (TypeError, ValueError):
            sequence = 0

        try:
            journey_day = max(1, int(row.get("day") or 1))
        except (TypeError, ValueError):
            journey_day = 1

        routes[number].append({
            "sequence": sequence,
            "stationCode": code,
            "stationName": name,
            "arrivalTime": str(row.get("arrival") or "").strip(),
            "departureTime": str(row.get("departure") or "").strip(),
            "journeyDay": journey_day,
            "distance": str(row.get("distance_km") or "").strip(),
        })

    # Use the station CSV as an additional source of station names.
    for row in station_rows:
        code = str(
            row.get("code") or row.get("station_code") or ""
        ).strip()

        name = str(
            row.get("name") or row.get("station_name") or ""
        ).strip()

        if code and name:
            station_names[code] = name

    trains = []

    for number, train in metadata.items():
        route = sorted(
            routes.get(number, []),
            key=lambda stop: stop["sequence"],
        )

        if len(route) < 2:
            continue

        train = dict(train)
        train["completeOrderedRoute"] = route
        trains.append(train)

    stations = [
        {"code": code, "name": name}
        for code, name in station_names.items()
    ]

    return {
        "stations": stations,
        "trains": trains,
        "excluded_types": sorted(EXCLUDED_TYPES),
    }


def station_options(data):
    found = {}

    for station in data["stations"]:
        code = str(station.get("code") or "").strip()
        name = str(station.get("name") or "").strip()

        if code and name:
            found[code] = name

    for train in data["trains"]:
        for stop in train["completeOrderedRoute"]:
            code = stop["stationCode"]
            name = stop["stationName"]
            found.setdefault(code, name or code)

    return {
        f"{name} ({code})": code
        for code, name in sorted(
            found.items(),
            key=lambda item: (item[1].casefold(), item[0]),
        )
    }
