from flask import Flask, request, jsonify
import requests
import os
import re
import dateparser

app = Flask(__name__)

# ENV
HF_TOKEN = os.environ.get("HF_API_TOKEN")
RAIL_API_KEY = os.environ.get("RAILWAY_API_KEY")
HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"}

# Hugging Face models
NER_URL = "https://api-inference.huggingface.co/models/dslim/bert-base-NER"
INTENT_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"

# Mapped intents
INTENT_LABELS = [
    "find trains between two stations",
    "check seat availability",
    "check train running status"
]
INTENT_MAP = {
    "find trains between two stations": "train_search",
    "check seat availability": "seat_availability",
    "check train running status": "train_status"
}

@app.route("/")
def home():
    return "🚆 Train Assistant is running!"

def get_station_code(name):
    try:
        url = f"https://indianrailapi.com/api/v2/StationSearch/apikey/{RAIL_API_KEY}/StationCodeOrName/{name}"
        res = requests.get(url, timeout=10)
        data = res.json()
        if data.get("ResponseCode") == "200" and data.get("Stations"):
            return data["Stations"][0]["StationCode"]
    except Exception as e:
        print(f"Station API error for {name}: {e}")
    return None

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")
    intent = "unknown"
    source = destination = date = train_no = None

    # Intent Detection
    try:
        intent_payload = {
            "inputs": user_input,
            "parameters": {"candidate_labels": INTENT_LABELS}
        }
        res = requests.post(INTENT_URL, headers=HEADERS, json=intent_payload, timeout=15).json()
        label = res.get("labels", [])[0]
        intent = INTENT_MAP.get(label, "unknown")
    except Exception as e:
        print("Intent error:", e)

    # Entity Extraction
    try:
        ner_res = requests.post(NER_URL, headers=HEADERS, json={"inputs": user_input}, timeout=10).json()
        for ent in ner_res:
            word = ent["word"].replace("##", "")
            entity = ent["entity_group"]
            if entity == "LOC":
                if not source:
                    source = word
                elif not destination:
                    destination = word
            elif entity == "CARDINAL" and word.isdigit():
                train_no = word
    except Exception as e:
        print("NER error:", e)

    # Regex fallback for locations and date
    try:
        src_match = re.search(r'from\s+([A-Za-z]+)', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+([A-Za-z]+)', user_input, re.IGNORECASE)
        date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)

        if src_match:
            source = src_match.group(1)
        if dest_match:
            destination = dest_match.group(1)
        if date_match:
            parsed_date = dateparser.parse(date_match.group(1))
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print("Regex fallback failed:", e)

    # Final date fallback
    if not date:
        parsed_date = dateparser.parse(user_input)
        if parsed_date:
            date = parsed_date.strftime("%Y-%m-%d")

    # Convert city names to station codes
    if source:
        source = get_station_code(source)
    if destination:
        destination = get_station_code(destination)

    result = {
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        }
    }

    # Final train search
    if intent == "train_search" and source and destination and date:
        try:
            url = f"https://indianrailapi.com/api/v2/TrainBetweenStations/apikey/{RAIL_API_KEY}/From/{source}/To/{destination}/Date/{date}/"
            train_res = requests.get(url, timeout=15).json()
            result["trains"] = train_res.get("Trains", [])
        except Exception as e:
            print("Train search error:", e)
            result["trains"] = []

    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True)
