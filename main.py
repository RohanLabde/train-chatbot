from flask import Flask, request, jsonify
import requests
import os
import re
import dateparser
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

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
        logging.info(f"User input: {user_input}")

        intent = "unknown"
        source = destination = date = train_no = None

        # --- 1. Intent Classification (ML-based) ---
        try:
            intent_payload = {
                "inputs": user_input,
                "parameters": {"candidate_labels": INTENT_LABELS}
            }
            intent_response = requests.post(INTENT_URL, headers=HEADERS, json=intent_payload, timeout=10)
            intent_data = intent_response.json()
            logging.info(f"HF Intent Response: {intent_data}")
            if "labels" in intent_data:
                intent = intent_data["labels"][0]
        except Exception as e:
            logging.warning(f"Intent classification failed: {e}")

        # --- 2. Keyword-based fallback intent classification ---
        if intent == "unknown" or intent == "train_status":
            lowered = user_input.lower()
            if re.search(r"(show|find|search|get).*train", lowered):
                intent = "train_search"
            elif re.search(r"(seat|availability|book.*seat)", lowered):
                intent = "seat_availability"
            elif re.search(r"(running|status|late|delay|arrival|departure)", lowered):
                intent = "train_status"

        # --- 3. Named Entity Recognition (NER) ---
        try:
            ner_payload = {"inputs": user_input}
            ner_response = requests.post(NER_URL, headers=HEADERS, json=ner_payload, timeout=10)
            ner_data = ner_response.json()
            logging.info(f"NER Response: {ner_data}")
            if isinstance(ner_data, list):
                for ent in ner_data:
                    entity = ent.get("entity_group", "")
                    word = ent.get("word", "").replace("##", "")
                    if entity == "LOC":
                        if not source:
                            source = word
                        elif not destination:
                            destination = word
                    elif entity == "DATE":
                        if not date:
                            date = word
                    elif entity == "CARDINAL" and word.isdigit():
                        train_no = word
        except Exception as e:
            logging.warning(f"NER error: {e}")

        # --- 4. Fallback Entity Extraction using Regex ---
        try:
            src_match = re.search(r'from\s+([a-zA-Z]+)', user_input, re.IGNORECASE)
            dest_match = re.search(r'to\s+([a-zA-Z]+)', user_input, re.IGNORECASE)
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
            logging.warning(f"Regex fallback error: {e}")

        # --- 5. Fallback full message date parsing ---
        try:
            if not date:
                parsed_date = dateparser.parse(user_input)
                if parsed_date:
                    date = parsed_date.strftime("%Y-%m-%d")
        except Exception as e:
            logging.warning(f"Date fallback error: {e}")

        result = {
            "intent": intent,
            "entities": {
                "source": source,
                "destination": destination,
                "date": date,
                "train_no": train_no
            }
        }

        # --- 6. Train Search API Integration ---
        if intent == "train_search" and source and destination and date:
            try:
                rail_url = f"https://indianrailapi.com/api/v2/TrainBetweenStations/apikey/{RAIL_API_KEY}/From/{source}/To/{destination}/Date/{date}/"
                rail_response = requests.get(rail_url, timeout=15)
                rail_data = rail_response.json()
                result["trains"] = rail_data.get("Trains", [])
            except Exception as e:
                logging.error(f"Indian Rail API error: {e}")
                result["trains"] = []

        return jsonify(result)

    except Exception as e:
        logging.error(f"Unexpected error in chatbot route: {e}")
        return jsonify({"error": "Something went wrong. Please try again later."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
