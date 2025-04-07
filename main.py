from flask import Flask, request, jsonify
import os
import json
import re
import logging
import dateparser
import pandas as pd
from difflib import get_close_matches

app = Flask(__name__)

# Load train route data from CSV
TRAIN_CSV_PATH = os.path.join("data", "isl_wise_train_detail_03082015_v1.csv")
TRAIN_ROUTE_MAP = {}
STATION_NAME_TO_CODE = {}
STATION_CODE_TO_NAME = {}

try:
    df = pd.read_csv(TRAIN_CSV_PATH)

    # Normalize station names and build maps
    for _, row in df.iterrows():
        train_no = str(row["Train No."]).strip()
        train_name = str(row["train Name"]).strip()
        station_code = str(row["station Code"]).strip().upper()
        station_name = str(row["Station Name"]).strip().upper()

        route_entry = {
            "station_code": station_code,
            "station_name": station_name,
            "arrival": row.get("Arrival time", ""),
            "departure": row.get("Departure time", ""),
            "distance": row.get("Distance", 0)
        }

        if train_no not in TRAIN_ROUTE_MAP:
            TRAIN_ROUTE_MAP[train_no] = {
                "train_no": train_no,
                "train_name": train_name,
                "route": []
            }

        TRAIN_ROUTE_MAP[train_no]["route"].append(route_entry)

        STATION_NAME_TO_CODE[station_name] = station_code
        STATION_CODE_TO_NAME[station_code] = station_name

    logging.info(f"✅ Loaded route data for {len(TRAIN_ROUTE_MAP)} trains and {len(STATION_NAME_TO_CODE)} stations")

except Exception as e:
    logging.error("❌ Failed to build station maps.", exc_info=True)

# Intent keyword map
FALLBACK_INTENTS = {
    "train_search": ["train from", "show me trains", "trains between", "train to"],
    "train_status": ["status", "running status"],
    "seat_availability": ["seats", "available", "seat availability"]
}

def resolve_station_name(input_name):
    if not input_name:
        return None
    name = input_name.upper().strip()
    if name in STATION_NAME_TO_CODE:
        return STATION_NAME_TO_CODE[name]
    if name in STATION_CODE_TO_NAME:
        return name
    match = get_close_matches(name, STATION_NAME_TO_CODE.keys(), n=1, cutoff=0.85)
    if match:
        return STATION_NAME_TO_CODE[match[0]]
    logging.warning(f"⚠️ Could not resolve station name: {input_name}")
    return None

@app.route("/")
def home():
    return "🚆 Static Train Chatbot is up and running!"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "").strip()

    source = destination = date = train_no = None
    intent = "unknown"
    trains_found = []

    try:
        for label, keywords in FALLBACK_INTENTS.items():
            for kw in keywords:
                if kw in user_input.lower():
                    intent = label
                    break
            if intent != "unknown":
                break
    except Exception as e:
        logging.warning("⚠️ Intent detection failed", exc_info=True)

    try:
        date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)
        src_match = re.search(r'from\s+([a-zA-Z\s]+)', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+([a-zA-Z\s]+)', user_input, re.IGNORECASE)

        if date_match:
            parsed_date = dateparser.parse(date_match.group(1))
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")

        if src_match:
            source = resolve_station_name(src_match.group(1))

        if dest_match:
            destination = resolve_station_name(dest_match.group(1))

    except Exception as e:
        logging.warning("⚠️ Entity extraction failed", exc_info=True)

    try:
        if intent == "train_search" and source and destination:
            for train in TRAIN_ROUTE_MAP.values():
                route = [r["station_code"] for r in train.get("route", [])]
                if source in route and destination in route:
                    if route.index(source) < route.index(destination):
                        trains_found.append({
                            "train_no": train["train_no"],
                            "train_name": train["train_name"],
                            "source": source,
                            "destination": destination
                        })
    except Exception as e:
        logging.error("❌ Error while searching trains", exc_info=True)

    return jsonify({
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        },
        "trains": trains_found
    })

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5000)
