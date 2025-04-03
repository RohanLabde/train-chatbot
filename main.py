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
    "train_status"
]

@app.route("/")
def home():
    return "🚆 Train Assistant is live using Hugging Face and Indian Rail API."

@app.route("/chatbot", methods=["POST"])
def chatbot():
    try:
        data = request.get_json()
        user_input = data.get("message", "")
        print(f"📥 Received user message: {user_input}")

        # 1. Intent Detection
        intent = "unknown"
        try:
            intent_payload = {
                "inputs": user_input,
                "parameters": {"candidate_labels": INTENT_LABELS}
            }
            intent_response = requests.post(INTENT_URL, headers=HEADERS, json=intent_payload, timeout=15)
            intent_data = intent_response.json()
            print(f"🧠 Intent Response: {intent_data}")
            if "labels" in intent_data:
                intent = intent_data["labels"][0]
        except Exception as e:
            print(f"❌ Intent classification error: {e}")

        # 2. Entity Recognition
        source = destination = date = train_no = None
        try:
            ner_payload = {"inputs": user_input}
            ner_response = requests.post(NER_URL, headers=HEADERS, json=ner_payload, timeout=15)
            ner_data = ner_response.json()
            print(f"📦 NER Response: {ner_data}")

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
            print(f"❌ NER error: {e}")

        # 3. Fallback Regex Entity Extraction
        try:
            src_match = re.search(r'from\s+([A-Za-z]+)', user_input, re.IGNORECASE)
            dest_match = re.search(r'to\s+([A-Za-z]+)', user_input, re.IGNORECASE)
            date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)

            if src_match:
                source = src_match.group(1).strip().upper()
            if dest_match:
                destination = dest_match.group(1).strip().upper()
            if date_match and not date:
                parsed_date = dateparser.parse(date_match.group(1))
                if parsed_date:
                    date = parsed_date.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"❌ Regex fallback error: {e}")

        # 4. Final Fallback Full Date Parsing
        try:
            if not date:
                parsed_date = dateparser.parse(user_input)
                if parsed_date:
                    date = parsed_date.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"❌ Final date parsing error: {e}")

        result = {
            "intent": intent,
            "entities": {
                "source": source,
                "destination": destination,
                "date": date,
                "train_no": train_no
            }
        }

        # 5. Train Search Integration
        if intent == "train_search" and source and destination and date:
            try:
                print(f"🔍 Fetching trains from {source} to {destination} on {date}")
                rail_url = f"https://indianrailapi.com/api/v2/TrainBetweenStations/apikey/{RAIL_API_KEY}/From/{source}/To/{destination}/Date/{date}/"
                rail_response = requests.get(rail_url, timeout=15)
                rail_data = rail_response.json()
                result["trains"] = rail_data.get("Trains", [])
            except Exception as e:
                print(f"❌ Indian Rail API error: {e}")
                result["trains"] = []

        return jsonify(result)

    except Exception as e:
        print(f"🔥 Critical /chatbot error: {e}")
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
