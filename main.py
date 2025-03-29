from flask import Flask, request, jsonify
import requests
import os
import re
import dateparser

app = Flask(__name__)

# API Keys from environment
HF_TOKEN = os.environ.get("HF_API_TOKEN")
RAIL_API_KEY = os.environ.get("RAILWAY_API_KEY")

# Hugging Face model endpoints
NER_URL = "https://api-inference.huggingface.co/models/dslim/bert-base-NER"
INTENT_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"

# Supported intents
INTENT_LABELS = [
    "train_search",
    "seat_availability",
    "train_status"
]

HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}"
}

@app.route("/")
def home():
    return "🚆 Train Assistant is running with dynamic station resolution!"

# 🔁 Resolve station name to code using Indian Rail API
def resolve_station_code(station_name):
    try:
        search_text = station_name.strip().replace(" ", "%20")
        url = f"http://indianrailapi.com/api/v2/StationCodeOrName/apikey/{RAIL_API_KEY}/SearchText/{search_text}/"
        res = requests.get(url, timeout=10)
        data = res.json()
        if data["Status"] == "SUCCESS" and data["Station"]:
            return data["Station"][0]["StationCode"].upper()
    except Exception as e:
        print(f"⚠️ Error resolving station code for {station_name}: {e}")
    return None

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")
    source = destination = date = train_no = None
    intent = "unknown"

    # --- 1. Intent Classification ---
    try:
        payload = {
            "inputs": user_input,
            "parameters": {"candidate_labels": INTENT_LABELS}
        }
        intent_response = requests.post(INTENT_URL, headers=HEADERS, json=payload, timeout=10)
        intent_data = intent_response.json()
        if "labels" in intent_data:
            intent = intent_data["labels"][0]
    except Exception as e:
        print("⚠️ Intent classification error:", str(e))

    # --- 2. NER Extraction ---
    try:
        ner_payload = {"inputs": user_input}
        ner_response = requests.post(NER_URL, headers=HEADERS, json=ner_payload, timeout=10)
        ner_data = ner_response.json()
        if isinstance(ner_data, list):
            for ent in ner_data:
                entity = ent.get("entity_group", "")
                word = ent.get("word", "").replace("##", "")
                if entity == "LOC":
                    if not source:
                        source = word
                    elif not destination:
                        destination = word
                elif entity == "DATE" and not date:
                    date = word
                elif entity == "CARDINAL" and word.isdigit():
                    train_no = word
    except Exception as e:
        print("⚠️ NER error:", str(e))

    # --- 3. Fallback Regex Extraction ---
    try:
        src_match = re.search(r'from\s+([A-Za-z ]+)', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+([A-Za-z ]+)', user_input, re.IGNORECASE)
        date_match = re.search(r'on\s+([A-Za-z0-9 ,]+)', user_input, re.IGNORECASE)

        if src_match:
            source = src_match.group(1).strip()
        if dest_match:
            destination = dest_match.group(1).strip()
        if date_match and not date:
            parsed = dateparser.parse(date_match.group(1))
            if parsed:
                date = parsed.strftime("%Y-%m-%d")
    except Exception as e:
        print("⚠️ Regex fallback error:", str(e))

    # --- 4. Final date fallback ---
    if not date:
        parsed = dateparser.parse(user_input)
        if parsed:
            date = parsed.strftime("%Y-%m-%d")

    # --- 5. Convert station names to codes ---
    source_code = resolve_station_code(source) if source else None
    dest_code = resolve_station_code(destination) if destination else None

    result = {
        "intent": intent,
        "entities": {
            "source": source_code,
            "destination": dest_code,
            "date": date,
            "train_no": train_no
        }
    }

    # --- 6. Call Train Search API ---
    if intent == "train_search" and source_code and dest_code and date:
        try:
            rail_url = f"https://indianrailapi.com/api/v2/TrainBetweenStations/apikey/{RAIL_API_KEY}/From/{source_code}/To/{dest_code}/Date/{date}/"
            rail_response = requests.get(rail_url, timeout=15)
            rail_data = rail_response.json()
            result["trains"] = rail_data.get("Trains", [])
        except Exception as e:
            print("⚠️ Indian Rail API error:", str(e))
            result["trains"] = []

    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
