from flask import Flask, request, jsonify
import os
import json
import re
import dateparser
import logging
from difflib import get_close_matches

app = Flask(__name__)

# --- Load static train data on startup ---
TRAIN_DATA_FILE = os.path.join("data", "final_train_data_by_train_no.json")
try:
    with open(TRAIN_DATA_FILE, "r", encoding="utf-8") as f:
        TRAIN_DATA = json.load(f)
    logging.info(f"✅ Loaded train data with {len(TRAIN_DATA)} trains.")
except Exception as e:
    logging.error("❌ Failed to load train data.", exc_info=True)
    TRAIN_DATA = {}

# --- Build station metadata ---
STATION_CODES = set()
STATION_NAMES = set()
STATION_NAME_TO_CODE = {}
CITY_NAME_TO_CODES = {}

try:
    for train in TRAIN_DATA.values():
        route = train.get("route", [])
        if isinstance(route, list):
            for stop in route:
                code = stop.get("station_code", "").upper()
                name = stop.get("station_name", "").upper()
                if not code or not name:
                    continue
                STATION_CODES.add(code)
                STATION_NAMES.add(name)
                STATION_NAME_TO_CODE[name] = code
                CITY_NAME_TO_CODES.setdefault(name, set()).add(code)
        else:
            logging.warning(f"Unexpected route format for train {train.get('train_no')}: {type(route)}")
    logging.info(f"✅ Built station maps with {len(STATION_CODES)} codes and {len(STATION_NAMES)} names.")
except Exception as e:
    logging.error("❌ Failed to build station maps.", exc_info=True)

# --- Intent keywords ---
FALLBACK_INTENTS = {
    "train_search": ["show me trains", "train between", "trains from", "train to"],
    "train_status": ["status", "live status", "running status"],
    "seat_availability": ["seats", "available", "check seat"]
}

def resolve_station_name(input_name):
    if not input_name:
        return None
    upper_input = input_name.strip().upper()

    if upper_input in STATION_CODES:
        return upper_input
    if upper_input in STATION_NAME_TO_CODE:
        return STATION_NAME_TO_CODE[upper_input]

    # Try fuzzy match on station names
    name_matches = get_close_matches(upper_input, STATION_NAMES, n=1, cutoff=0.75)
    if name_matches:
        match = name_matches[0]
        logging.info(f"✅ Fuzzy matched station name '{input_name}' to '{match}'")
        return STATION_NAME_TO_CODE.get(match)

    # Try fuzzy match on station codes
    code_matches = get_close_matches(upper_input, STATION_CODES, n=1, cutoff=0.75)
    if code_matches:
        logging.info(f"✅ Fuzzy matched code '{input_name}' to '{code_matches[0]}'")
        return code_matches[0]

    logging.warning(f"⚠️ Could not resolve station: {input_name}")
    return None

@app.route("/")
def home():
    return "🚆 Static Train Assistant is live with fuzzy search!"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "").strip()

    source = destination = date = train_no = None
    intent = "unknown"
    trains_found = []

    # --- Intent fallback logic ---
    try:
        for label, keywords in FALLBACK_INTENTS.items():
            for kw in keywords:
                if kw.lower() in user_input.lower():
                    intent = label
                    break
            if intent != "unknown":
                break
    except Exception as e:
        logging.warning("Intent fallback failed", exc_info=True)

    # --- Entity extraction using regex ---
    try:
        date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)
        src_match = re.search(r'from\s+([\w]+)', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+([\w]+)', user_input, re.IGNORECASE)

        if date_match:
            parsed_date = dateparser.parse(date_match.group(1))
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")

        if src_match:
            source_name = src_match.group(1)
            source = resolve_station_name(source_name)

        if dest_match:
            dest_name = dest_match.group(1)
            destination = resolve_station_name(dest_name)

        logging.info(f"🔎 Extracted source={source}, destination={destination}, date={date}")

    except Exception as e:
        logging.warning("Regex-based entity extraction failed", exc_info=True)

    # --- Train search using static data ---
    if intent == "train_search" and source and destination:
        try:
            for train in TRAIN_DATA.values():
                route = train.get("route", [])
                if not isinstance(route, list):
                    continue
                stations = [s.get("station_code") for s in route]
                if source in stations and destination in stations:
                    src_index = stations.index(source)
                    dest_index = stations.index(destination)
                    if src_index < dest_index:
                        trains_found.append({
                            "train_no": train.get("train_no"),
                            "train_name": train.get("train_name"),
                            "source": source,
                            "destination": destination
                        })
        except Exception as e:
            logging.error("❌ Error during train search", exc_info=True)

    result = {
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        },
        "trains": trains_found
    }

    return jsonify(result)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5000)
