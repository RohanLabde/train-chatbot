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

# Hugging Face model endpoints
NER_URL = "https://api-inference.huggingface.co/models/dslim/bert-base-NER"
INTENT_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"

# Updated intent labels for better matching
INTENT_LABELS = [
    "search trains between stations",
    "check seat availability",
    "check train running status"
]

# Mapping descriptive labels back to internal keys
INTENT_MAP = {
    "search trains between stations": "train_search",
    "check seat availability": "seat_availability",
    "check train running status": "train_status"
}

@app.route("/")
def home():
    return "🚆 Train Assistant is running with Hugging Face & Indian Rail APIs!"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")
    
    # Initialize
    intent = "unknown"
    source = destination = date = train_no = None

    # --- 1. Intent Detection ---
    try:
        intent_payload = {
            "inputs": user_input,
            "parameters": {"candidate_labels": list(INTENT_MAP.keys())}
        }
        intent_response = requests.post(INTENT_URL, headers=HEADERS, json=intent_payload, timeout=10)
        intent_data = intent_response.json()
        if "labels" in intent_data:
            best_label = intent_data["labels"][0]
            intent = INTENT_MAP.get(best_label, "unknown")
    except Exception as e:
        print("⚠️ Intent detection failed:", str(e))

    # --- 2. Entity Extraction via NER ---
    try:
        ner_response = requests.post(NER_URL, headers=HEADERS, json={"inputs": user_input}, timeout=10)
        ner_data = ner_response.json()
        if isinstance(ner_data, list):
            for ent in ner_data:
                entity = ent.get("entity_group", "")
                word = ent.get("word", "").replace("##", "")
                if entity == "LOC":
                    if not source:
                        source = word.upper()
                    elif not destination:
                        destination = word.upper()
                elif entity == "DATE" and not date:
                    date = word
                elif entity == "CARDINAL" and word.isdigit():
                    train_no = word
    except Exception as e:
        print("⚠️ NER failed:", str(e))

    # --- 3. Regex Fallback for Entity Extraction ---
    try:
        src_match = re.search(r'from\s+([A-Z]{3,4})', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+([A-Z]{3,4})', user_input, re.IGNORECASE)
        date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)

        if src_match:
            source = src_match.group(1).upper()
        if dest_match:
            destination = dest_match.group(1).upper()
        if date_match and not date:
            parsed_date = dateparser.parse(date_match.group(1))
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print("⚠️ Regex fallback failed:", str(e))

    # --- 4. Full fallback to extract date ---
    try:
        if not date:
            parsed_date = dateparser.parse(user_input)
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print("⚠️ Date parsing failed:", str(e))

    # --- 5. Prepare response ---
    result = {
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        }
    }

    # --- 6. Query Indian Rail API if needed ---
    if intent == "train_search" and source and destination and date:
        try:
            rail_url = f"https://indianrailapi.com/api/v2/TrainBetweenStations/apikey/{RAIL_API_KEY}/From/{source}/To/{destination}/Date/{date}/"
            rail_response = requests.get(rail_url, timeout=15)
            rail_data = rail_response.json()
            result["trains"] = rail_data.get("Trains", [])
        except Exception as e:
            print("⚠️ Indian Rail API failed:", str(e))
            result["trains"] = []

    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
