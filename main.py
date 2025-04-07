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

# --- Build station maps ---
STATION_NAMES = set()
STATION_CODES = set()
STATION_NAME_TO_CODE = {}

try:
    for train in TRAIN_DATA.values():
        if isinstance(train, dict):
            for stop in train.get("route", []):
                name = stop.get("station_name", "").strip().upper()
                code = stop.get("station_code", "").strip().upper()
                if name and code:
                    STATION_NAMES.add(name)
                    STATION_CODES.add(code)
                    STATION_NAME_TO_CODE[name] = code
    logging.info(f"✅ Built station maps with {len(STATION_NAME_TO_CODE)} unique station names.")
except Exception as e:
    logging.error("❌ Failed to build station maps.", exc_info=True)

# --- Supported intent keywords ---
FALLBACK_INTENTS = {
    "train_search": ["show me trains", "train between", "trains from", "train to"],
    "train_status": ["status", "live status", "running status"],
    "seat_availability": ["seats", "available", "check seat"]
}

def resolve_station_name(input_name):
    try:
        input_clean = input_name.strip().upper()
        logging.info(f"🔍 Resolving station name for input: {input_clean}")

        if input_clean in STATION_CODES:
            logging.info(f"✅ Matched as station code: {input_clean}")
            return input_clean

        if input_clean in STATION_NAME_TO_CODE:
            logging.info(f"✅ Matched full station name: {input_clean}")
            return STATION_NAME_TO_CODE[input_clean]

        # Fuzzy match with difflib
        fuzzy = get_close_matches(input_clean, STATION_NAME_TO_CODE.keys(), n=1, cutoff=0.7)
        if fuzzy:
            logging.info(f"✅ Fuzzy matched to: {fuzzy[0]}")
            return STATION_NAME_TO_CODE[fuzzy[0]]

        # Substring match
        for name in STATION_NAME_TO_CODE:
            if input_clean in name:
                logging.info(f"✅ Substring matched to: {name}")
                return STATION_NAME_TO_CODE[name]

        logging.warning(f"❌ No match found for: {input_clean}")
        return None
    except Exception as e:
        logging.error("❌ Error during station resolution", exc_info=True)
        return None

@app.route("/")
def home():
    return "🚆 Static Train Assistant is live with fuzzy matching!"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    try:
        data = request.get_json()
        user_input = data.get("message", "").strip()

        source = destination = date = train_no = None
        intent = "unknown"
        trains_found = []

        # --- Intent fallback logic ---
        for label, keywords in FALLBACK_INTENTS.items():
            for kw in keywords:
                if kw.lower() in user_input.lower():
                    intent = label
                    break
            if intent != "unknown":
                break

        # --- Entity extraction using regex ---
        date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)
        src_match = re.search(r'from\s+(\w+)', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+(\w+)', user_input, re.IGNORECASE)

        if date_match:
            parsed_date = dateparser.parse(date_match.group(1))
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")

        if src_match:
            source_raw = src_match.group(1)
            source = resolve_station_name(source_raw)

        if dest_match:
            dest_raw = dest_match.group(1)
            destination = resolve_station_name(dest_raw)

        # --- Train search using static data ---
        if intent == "train_search" and source and destination:
            for train in TRAIN_DATA.values():
                stations = [s.get("station_code") for s in train.get("route", [])]
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
    except Exception as e:
        logging.error("❌ Unexpected error in chatbot handler", exc_info=True)
        return jsonify({"error": "Unexpected server error."}), 500

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5000)
