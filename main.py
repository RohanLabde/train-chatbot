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

# Supported intent labels
INTENT_LABELS = [
    "train_search",
    "seat_availability",
    "book_ticket",
    "cancel_ticket",
    "train_status"
]

@app.route("/")
def home():
    return "🚆 Train Assistant is live using Hugging Face and Indian Rail API."

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")
    intent = "unknown"
    source = destination = date = train_no = None

    # --- 1. Intent Classification ---
    try:
        intent_payload = {
            "inputs": user_input,
            "parameters": {"candidate_labels": INTENT_LABELS}
        }
        intent_response = requests.post(INTENT_URL, headers=HEADERS, json=intent_payload, timeout=10)
        intent_data = intent_response.json()
        if "labels" in intent_data and "scores" in intent_data:
            intent_scores = dict(zip(intent_data["labels"], intent_data["scores"]))
            intent = max(intent_scores, key=intent_scores.get)
            print("Intent Scores:", intent_scores)
    except Exception as e:
        print("\u26a0\ufe0f Intent classification error:", str(e))

    # --- 2. Named Entity Recognition (NER) ---
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
        print("\u26a0\ufe0f NER error:", str(e))

    # --- 3. Fallback Entity Extraction with Regex ---
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
        print("\u26a0\ufe0f Regex fallback error:", str(e))

    # --- 4. Full-sentence fallback date parsing ---
    try:
        if not date:
            parsed_date = dateparser.parse(user_input)
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print("\u26a0\ufe0f Dateparser fallback error:", str(e))

    result = {
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        }
    }

    # --- 5. Train Search using Indian Rail API ---
    if intent == "train_search" and source and destination and date:
        try:
            rail_url = f"https://indianrailapi.com/api/v2/TrainBetweenStations/apikey/{RAIL_API_KEY}/From/{source}/To/{destination}/Date/{date}/"
            rail_response = requests.get(rail_url, timeout=15)
            rail_data = rail_response.json()
            result["trains"] = rail_data.get("Trains", [])
        except Exception as e:
            print("\u26a0\ufe0f Indian Rail API error:", str(e))
            result["trains"] = []

    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
