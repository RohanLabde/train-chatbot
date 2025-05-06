from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import re
import dateparser
import logging
from difflib import get_close_matches

app = Flask(__name__)
CORS(app)

# --- Load and transform static train data ---
TRAIN_DATA_FILE = os.path.join("data", "final_train_data_by_train_no.json")
TRAIN_DATA = []

try:
    with open(TRAIN_DATA_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, dict):
        for raw_train_no, stops in raw_data.items():
            train_no = raw_train_no.strip().replace("'", "")
            if stops and isinstance(stops, list):
                train_name = stops[0].get("Train_Name", "").strip()
                route = []
                for stop in stops:
                    route.append({
                        "station_name": stop.get("Station_Name", "").strip().upper(),
                        "station_code": stop.get("Station_Code", "").strip().upper(),
                        "arrival": stop.get("Arrival_Time", "").strip().replace("'", ""),
                        "departure": stop.get("Departure_Time", "").strip().replace("'", "")
                    })
                TRAIN_DATA.append({
                    "train_no": train_no,
                    "train_name": train_name,
                    "route": route
                })
    else:
        raise ValueError("Train data is not in expected dictionary format")

    logging.info(f"✅ Loaded train data: {len(TRAIN_DATA)} trains.")
except Exception as e:
    logging.error("❌ Failed to load or validate train data.", exc_info=True)
    TRAIN_DATA = []

# --- Build a set of station names and codes ---
STATION_NAME_CODE_PAIRS = set()
if TRAIN_DATA:
    for train in TRAIN_DATA:
        for stop in train.get("route", []):
            name = stop.get("station_name", "").strip().upper()
            code = stop.get("station_code", "").strip().upper()
            if name and code:
                STATION_NAME_CODE_PAIRS.add((name, code))
    logging.info(f"✅ Built station map with {len(STATION_NAME_CODE_PAIRS)} entries.")
else:
    logging.warning("⚠️ TRAIN_DATA is empty. Station map cannot be built.")

# --- Helper to resolve station name to code using fuzzy matching ---
def resolve_station_name(input_text):
    input_text = input_text.strip().upper()
    all_names = [name for name, _ in STATION_NAME_CODE_PAIRS]
    all_codes = [code for _, code in STATION_NAME_CODE_PAIRS]

    if input_text in all_codes:
        return input_text

    for name, code in STATION_NAME_CODE_PAIRS:
        if name == input_text:
            return code

    match = get_close_matches(input_text, all_names, n=1, cutoff=0.75)
    if match:
        best_match = match[0]
        for name, code in STATION_NAME_CODE_PAIRS:
            if name == best_match:
                return code

    logging.warning(f"⚠️ Could not resolve station name: {input_text}")
    return None

# --- Supported intent keywords ---
FALLBACK_INTENTS = {
    "train_search": ["show me trains", "train between", "trains from", "train to"],
    "train_status": ["status", "live status", "running status"],
    "seat_availability": ["seats", "available", "check seat"]
}

@app.route("/")
def home():
    return "🚆 Static Train Assistant is live with correct TRAIN_DATA loading!"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "").strip()

    source = destination = date = None
    intent = "unknown"
    trains_found = []

    # --- Intent classification ---
    try:
        for label, keywords in FALLBACK_INTENTS.items():
            if any(kw.lower() in user_input.lower() for kw in keywords):
                intent = label
                break
    except Exception as e:
        logging.warning("Intent fallback failed", exc_info=True)

    # --- Entity extraction ---
    try:
        date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)
        src_match = re.search(r'from\s+([\w\s]+?)(?:\s+to|\s+on|$)', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+([\w\s]+?)(?:\s+on|$)', user_input, re.IGNORECASE)

        if date_match:
            parsed_date = dateparser.parse(date_match.group(1))
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")

        if src_match:
            source = resolve_station_name(src_match.group(1).strip())

        if dest_match:
            destination = resolve_station_name(dest_match.group(1).strip())

    except Exception as e:
        logging.warning("Regex-based entity extraction failed", exc_info=True)

    # --- Train matching logic ---
    if intent == "train_search" and source and destination:
        try:
            for train in TRAIN_DATA:
                stations = [s.get("station_code") for s in train.get("route", [])]
                if source in stations and destination in stations:
                    src_index = stations.index(source)
                    dest_index = stations.index(destination)
                    if src_index < dest_index:
                        src_departure = train["route"][src_index].get("departure")
                        dest_arrival = train["route"][dest_index].get("arrival")
                        trains_found.append({
                            "train_no": train.get("train_no"),
                            "train_name": train.get("train_name"),
                            "source": source,
                            "destination": destination,
                            "source_departure": src_departure,
                            "destination_arrival": dest_arrival
                        })

            # ✅ Sort by departure time
            trains_found.sort(key=lambda t: t.get("source_departure") or "99:99:99")

        except Exception as e:
            logging.error("❌ Error during train search", exc_info=True)

    # --- Final response ---
    result = {
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date
        },
        "trains": trains_found
    }

    return jsonify(result)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5000)
