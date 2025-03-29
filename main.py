from flask import Flask, request, jsonify
import requests
import os
import re
import dateparser

app = Flask(__name__)

# Hugging Face API setup
HF_TOKEN = os.environ.get("HF_API_TOKEN")
HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"}

# Indian Rail API Key
RAIL_API_KEY = os.environ.get("RAILWAY_API_KEY")

# Hugging Face model endpoints
NER_URL = "https://api-inference.huggingface.co/models/dslim/bert-base-NER"
INTENT_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"

# Intent Labels (only supported ones)
INTENT_LABELS = ["train_search", "seat_availability", "train_status"]

@app.route("/")
def home():
    return "🚆 Train Assistant with robust NLP + station code resolution"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")

    intent = "unknown"
    source = destination = date = train_no = None

    # --- 1. Attempt intent classification ---
    try:
        payload = {
            "inputs": user_input,
            "parameters": {"candidate_labels": INTENT_LABELS}
        }
        res = requests.post(INTENT_URL, headers=HEADERS, json=payload, timeout=15)
        intent_data = res.json()
        if "labels" in intent_data:
            intent = intent_data["labels"][0]
    except Exception as e:
        print("Intent classification failed:", str(e))

    # --- 2. NLP entity detection via NER ---
    try:
        ner_res = requests.post(NER_URL, headers=HEADERS, json={"inputs": user_input}, timeout=15)
        ner_data = ner_res.json()
        if isinstance(ner_data, list):
            for ent in ner_data:
                word = ent.get("word", "").replace("##", "")
                label = ent.get("entity_group", "")
                if label == "LOC":
                    if not source:
                        source = word
                    elif not destination:
                        destination = word
                elif label == "CARDINAL" and word.isdigit():
                    train_no = word
    except Exception as e:
        print("NER failed:", str(e))

    # --- 3. Regex fallback for better coverage ---
    try:
        match = re.search(r'from\s+(.*?)\s+to\s+(.*?)\s+(on|for)', user_input, re.IGNORECASE)
        if match:
            source = match.group(1).strip()
            destination = match.group(2).strip()

        # Extract date if available
        date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)
        if date_match:
            parsed = dateparser.parse(date_match.group(1))
            if parsed:
                date = parsed.strftime("%Y-%m-%d")
    except Exception as e:
        print("Regex fallback failed:", str(e))

    # --- 4. Final fallback for full input date parsing ---
    if not date:
        try:
            parsed = dateparser.parse(user_input)
            if parsed:
                date = parsed.strftime("%Y-%m-%d")
        except:
            pass

    # --- 5. Map station names to codes using IndianRailAPI ---
    def get_station_code(name):
        try:
            url = f"https://indianrailapi.com/api/v2/StationSearch/apikey/{RAIL_API_KEY}/StationName/{name}"
            r = requests.get(url, timeout=10)
            js = r.json()
            if js.get("ResponseCode") == "200":
                return js.get("Stations")[0].get("StationCode")
        except:
            return None

    source_code = get_station_code(source) if source else None
    destination_code = get_station_code(destination) if destination else None

    # --- 6. Train search logic if all values present ---
    result = {
        "intent": intent,
        "entities": {
            "source": source_code,
            "destination": destination_code,
            "date": date,
            "train_no": train_no
        }
    }

    if intent == "train_search" and source_code and destination_code and date:
        try:
            url = f"https://indianrailapi.com/api/v2/TrainBetweenStations/apikey/{RAIL_API_KEY}/From/{source_code}/To/{destination_code}/Date/{date}/"
            response = requests.get(url, timeout=15)
            trains = response.json().get("Trains", [])
            result["trains"] = trains
        except Exception as e:
            print("Train API call failed:", str(e))
            result["trains"] = []

    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
