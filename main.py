from flask import Flask, request, jsonify
import requests
import os
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

INTENT_LABELS = [
    "train_search",
    "seat_availability",
    "book_ticket",
    "cancel_ticket",
    "train_status"
]

@app.route("/")
def home():
    return "🚆 Train Assistant is running with Hugging Face APIs and Indian Rail integration!"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")

    # --- 1. Intent Classification ---
    intent = "unknown"
    try:
        intent_payload = {
            "inputs": user_input,
            "parameters": {"candidate_labels": INTENT_LABELS}
        }
        intent_response = requests.post(INTENT_URL, headers=HEADERS, json=intent_payload, timeout=15)
        intent_data = intent_response.json()
        if isinstance(intent_data, dict) and "labels" in intent_data:
            intent = intent_data["labels"][0]
    except Exception as e:
        print("Intent classification error:", e)

    # --- 2. Entity Recognition ---
    source = destination = date = train_no = None
    try:
        ner_payload = {"inputs": user_input}
        ner_response = requests.post(NER_URL, headers=HEADERS, json=ner_payload, timeout=15)
        ner_data = ner_response.json()
        if isinstance(ner_data, list):
            for ent in ner_data:
                entity = ent.get("entity_group", "")
                word = ent.get("word", "")
                if entity == "LOC":
                    if not source:
                        source = word
                    elif not destination:
                        destination = word
                elif entity == "DATE":
                    date = word
                elif entity == "CARDINAL" and word.isdigit():
                    train_no = word
    except Exception as e:
        print("NER error:", e)

    # --- 3. Fallback date parsing ---
    try:
        if not date:
            parsed_date = dateparser.parse(user_input)
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print("Dateparser error:", e)

    result = {
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        }
    }

    # --- 4. If intent is train_search, call Indian Rail API ---
    if intent == "train_search" and source and destination and date:
        try:
            source = source.upper()
            destination = destination.upper()
            rail_url = f"https://indianrailapi.com/api/v2/TrainBetweenStations/apikey/{RAIL_API_KEY}/From/{source}/To/{destination}/Date/{date}/"
            rail_response = requests.get(rail_url, timeout=20)
            rail_data = rail_response.json()
            result["trains"] = rail_data.get("Trains", [])
        except Exception as e:
            print("Railway API error:", e)
            result["trains"] = []

    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
