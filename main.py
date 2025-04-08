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
        raw_data = json.load(f)

    if isinstance(raw_data, list):
        TRAIN_DATA = {train.get("train_no"): train for train in raw_data if "train_no" in train}
    else:
        TRAIN_DATA = raw_data

    logging.info(f"✅ Loaded train data with {len(TRAIN_DATA)} trains.")

    # Log a few samples to verify structure
    for i, (train_no, train_info) in enumerate(TRAIN_DATA.items()):
        logging.info(f"📦 Sample Train {i+1}: {train_no} - {train_info.get('train_name')}")
        if i >= 4:
            break
except Exception as e:
    logging.error("❌ Failed to load or validate train data.", exc_info=True)
    TRAIN_DATA = {}

# --- Build a set of station names and codes ---
STATION_NAME_CODE_PAIRS = set()
try:
    for train in TRAIN_DATA.values():
        if isinstance(train, dict):
            for stop in train.get("route", []):
                name = stop.get("station_name", "").strip().upper()
                code = stop.get("station_code", "").strip().upper()
                if name and code:
                    STATION_NAME_CODE_PAIRS.add((name, code))
    logging.info(f"✅ Built station name-code map with {len(STATION_NAME_CODE_PAIRS)} entries.")
except Exception as e:
    logging.warning("⚠️ TRAIN_DATA is empty. Station map cannot be built.", exc_info=True)

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
    return "🚆 Static Train Assistant is live with improved fuzzy matching!"

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
                if kw.lower() in user_input.lower():
                    intent = label
                    break
            if intent != "unknown":
                break
    except Exception as e:
        logging.warning("Intent fallback failed", exc_info=True)

    try:
        date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)
        src_match = re.search(r'from\s+([\w\s]+?)(?:\s+to|\s+on|$)', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+([\w\s]+?)(?:\s+on|$)', user_input, re.IGNORECASE)

        if date_match:
            parsed_date = dateparser.parse(date_match.group(1))
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")

        if src_match:
            src_text = src_match.group(1).strip()
            source = resolve_station_name(src_text)

        if dest_match:
            dest_text = dest_match.group(1).strip()
            destination = resolve_station_name(dest_text)

    except Exception as e:
        logging.warning("Regex-based entity extraction failed", exc_info=True)

    if intent == "train_search" and source and destination:
        try:
            for train in TRAIN_DATA.values():
                stations = [s.get("station_code") for s in train.get("route", [])]
                if source in stations and destination in stations:
                    src_index = stations.index(source)
                    dest_index = stations.index(destination)
                    if src_index < dest_index:
                        trains_found.append({
                            "train_no": train["train_no"],
                            "train_name": train["train_name"],
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
