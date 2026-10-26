
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
RAW_DIR = PROJECT_DIR / "data" / "raw"

TRAINS_FILE = RAW_DIR / "trains.json"
STOPS_FILE = RAW_DIR / "stops.json"


def main():
    if not TRAINS_FILE.exists():
        raise FileNotFoundError(f"Missing file: {TRAINS_FILE}")

    print("Reading trains.json...")
    with TRAINS_FILE.open("r", encoding="utf-8-sig") as file:
        trains = json.load(file)

    if not isinstance(trains, list):
        raise ValueError("Expected trains.json to contain a JSON list.")

    total_stops = 0
    valid_trains = 0

    print("Extracting ordered train stops...")

    with STOPS_FILE.open("w", encoding="utf-8") as output:
        output.write("[\n")
        first_record = True

        for train_index, train in enumerate(trains):
            if not isinstance(train, dict):
                continue

            route = train.get("completeOrderedRoute")
            if not isinstance(route, list):
                continue

            train_number = str(train.get("trainNumber") or "").strip()
            train_name = str(train.get("trainName") or "").strip()

            if not train_number:
                continue

            valid_trains += 1

            for route_index, stop in enumerate(route):
                if not isinstance(stop, dict):
                    continue

                station_code = str(
                    stop.get("stationCode") or ""
                ).strip()

                if not station_code:
                    continue

                record = {
                    "trainIndex": train_index,
                    "trainNumber": train_number,
                    "trainName": train_name,
                    "sequence": stop.get("sequence", route_index),
                    "stationCode": station_code,
                    "stationName": stop.get("stationName"),
                    "arrivalTime": stop.get("arrivalTime"),
                    "departureTime": stop.get("departureTime"),
                    "journeyDay": stop.get("journeyDay"),
                    "distance": stop.get("distance"),
                    "runningDays": train.get("runningDays"),
                }

                if not first_record:
                    output.write(",\n")

                json.dump(
                    record,
                    output,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )

                first_record = False
                total_stops += 1

        output.write("\n]\n")

    print("\nStops JSON created successfully.")
    print(f"Train records processed: {valid_trains:,}")
    print(f"Stop records written: {total_stops:,}")
    print(f"Output file: {STOPS_FILE}")
    print(f"Output size: {STOPS_FILE.stat().st_size / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    main()
