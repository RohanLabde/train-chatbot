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

# --- Build a set of station names and codes ---
STATION_NAMES = set()
STATION_CODES = set()
STATION_NAME_TO_CODE = {}

try:
    for train in TRAIN_DATA.values():
        if isinstance(train, list):
            for stop in train:
                code = stop.get("station_code", "").upper()
                name = stop.get("station_name", "").upper()
                STATION_CODES.add(code)
                STATION_NAMES.add(name)
                STATION_NAME_TO_CODE[name] = code
except Exception as e:
    logging.error("❌ Failed to build station maps.", exc_info=True)

# --- Supported intent keywords ---
FALLBACK_INTENTS = {
    "train_search": ["show me trains", "train between", "trains from", "train to"],
    "train_status": ["status", "live status", "running status"],
    "seat_availability": ["seats", "available", "check seat"]
}

def resolve_station_name(input_name):
    upper_input = input_name.upper()
    if upper_input in STATION_NAME_TO_CODE:
        return STATION_NAME_TO_CODE[upper_input]
    elif upper_input in STATION_CODES:
        return upper_input
    else:
        # Try fuzzy match on station names
        match = get_close_matches(upper_input, STATION_NAMES, n=1, cutoff=0.8)
        if match:
            return STATION_NAME_TO_CODE[match[0]]
    return None

@app.route("/")
def home():
    return "🚆 Static Train Assistant is live with offline search!"

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
        src_match = re.search(r'from\s+(\w+)', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+(\w+)', user_input, re.IGNORECASE)

        if date_match:
            parsed_date = dateparser.parse(date_match.group(1))
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")

        if src_match:
            source = resolve_station_name(src_match.group(1))

        if dest_match:
            destination = resolve_station_name(dest_match.group(1))

    except Exception as e:
        logging.warning("Regex-based entity extraction failed", exc_info=True)

    # --- Train search using static data ---
    if intent == "train_search" and source and destination:
        try:
            for train in TRAIN_DATA.values():
                if isinstance(train, list):
                    stations = [s.get("station_code") for s in train if isinstance(s, dict)]
                    if source in stations and destination in stations:
                        src_index = stations.index(source)
                        dest_index = stations.index(destination)
                        if src_index < dest_index:
                            trains_found.append({
                                "train_no": next((tno for tno, tdata in TRAIN_DATA.items() if tdata == train), None),
                                "train_name": train[0].get("train_name", "Unknown"),
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
