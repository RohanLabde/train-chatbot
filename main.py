from flask import Flask, request, jsonify
import requests
import os
import re
import dateparser

app = Flask(__name__)

# Hugging Face API setup
HF_TOKEN = os.environ.get("HF_API_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}"
}

# Indian Rail API Key
RAIL_API_KEY = os.environ.get("RAILWAY_API_KEY")
STATION_API = f"https://indianrailapi.com/api/v2/StationSearch/apikey/{RAIL_API_KEY}/StationCodeOrName/"

# Train Between Stations API
TRAIN_SEARCH_API = "https://indianrailapi.com/api/v2/TrainBetweenStations/apikey/{key}/From/{src}/To/{dst}/Date/{dt}/"

# Hugging Face model endpoints
NER_URL = "https://api-inference.huggingface.co/models/dslim/bert-base-NER"
INTENT_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"

# Supported intent labels
INTENT_LABELS = ["train_search", "seat_availability", "train_status"]

def classify_intent(text):
    try:
        payload = {
            "inputs": text,
            "parameters": {"candidate_labels": INTENT_LABELS}
        }
        response = requests.post(INTENT_URL, headers=HEADERS, json=payload, timeout=15)
        data = response.json()
        return data["labels"][0] if "labels" in data else "unknown"
    except Exception as e:
        print("Intent error:", e)
        return "unknown"

def extract_entities(text):
    source = destination = date = train_no = None

    # Step 1: Try with Hugging Face NER
    try:
        ner_payload = {"inputs": text}
        response = requests.post(NER_URL, headers=HEADERS, json=ner_payload, timeout=15)
        entities = response.json()

        locs = []
        for ent in entities:
            if ent.get("entity_group") == "LOC":
                locs.append(ent.get("word", "").replace("##", "").strip())
            elif ent.get("entity_group") == "CARDINAL" and ent.get("word", "").isdigit():
                train_no = ent.get("word")
            elif ent.get("entity_group") == "DATE":
                date = ent.get("word")

        if len(locs) >= 2:
            source, destination = locs[:2]
    except Exception as e:
        print("NER error:", e)

    # Step 2: Fallback with regex + dateparser
    try:
        if not source:
            m = re.search(r"from\s+(\w+)", text, re.IGNORECASE)
            if m:
                source = m.group(1)

        if not destination:
            m = re.search(r"to\s+(\w+)", text, re.IGNORECASE)
            if m:
                destination = m.group(1)

        if not date:
            m = re.search(r"on\s+([\w\s]+)", text, re.IGNORECASE)
            if m:
                parsed_date = dateparser.parse(m.group(1))
                if parsed_date:
                    date = parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print("Regex fallback error:", e)

    return source, destination, date, train_no

def resolve_station_code(name):
    try:
        response = requests.get(STATION_API + name, timeout=10)
        data = response.json()
        if data.get("ResponseCode") == "200" and data.get("Stations"):
            return data["Stations"][0]["StationCode"]
    except Exception as e:
        print("Station code resolution error:", e)
    return None

@app.route("/")
def home():
    return "Train Assistant is up. 🚆"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    message = data.get("message", "")
    intent = classify_intent(message)
    source, destination, date, train_no = extract_entities(message)

    # Resolve station names to codes
    if source and len(source) > 3:
        source = resolve_station_code(source)
    if destination and len(destination) > 3:
        destination = resolve_station_code(destination)

    result = {
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        }
    }

    if intent == "train_search" and source and destination and date:
        try:
            url = TRAIN_SEARCH_API.format(key=RAIL_API_KEY, src=source, dst=destination, dt=date)
            trains = requests.get(url, timeout=15).json().get("Trains", [])
            result["trains"] = trains
        except Exception as e:
            print("Train search error:", e)
            result["trains"] = []

    return jsonify(result)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
