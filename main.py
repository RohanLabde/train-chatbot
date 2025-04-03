from flask import Flask, request, jsonify
import requests
import os
import re
import dateparser
import time

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

# Basic keyword-based fallback for intent detection
INTENT_KEYWORDS = {
    "train_search": ["show me trains", "search trains", "find trains", "train from", "train between"],
    "seat_availability": ["check seat", "seat availability", "available seat", "is seat"],
    "train_status": ["status of train", "train status", "running status", "live status"]
}

def fallback_intent_classifier(text):
    lowered = text.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                return intent
    return "unknown"

def fetch_trains_with_retries(rail_url, max_retries=3, backoff_factor=2):
    for attempt in range(max_retries):
        try:
            print(f"🔁 Attempt {attempt + 1} to fetch train data...")
            response = requests.get(rail_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("ResponseCode") == "202":
                    print("⚠️ Server busy. Retrying...")
                else:
                    return data.get("Trains", [])
            else:
                print(f"⚠️ Non-200 response: {response.status_code}")
        except Exception as e:
            print(f"❌ Error on attempt {attempt + 1}: {str(e)}")

        sleep_time = backoff_factor ** attempt
        print(f"⏳ Waiting for {sleep_time} seconds before retry...")
        time.sleep(sleep_time)

    print("❌ All retries failed.")
    return []

@app.route("/")
def home():
    return "🚆 Train Assistant is live using Hugging Face and Indian Rail API."

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")
    intent = "unknown"
    source = destination = date = train_no = None

    # 1. Intent Classification
    try:
        intent_payload = {
            "inputs": user_input,
            "parameters": {"candidate_labels": INTENT_LABELS}
        }
        intent_response = requests.post(INTENT_URL, headers=HEADERS, json=intent_payload, timeout=10)
        intent_data = intent_response.json()
        if "labels" in intent_data:
            intent = intent_data["labels"][0]
    except Exception as e:
        print("⚠️ Intent classification error:", str(e))

    # Fallback using keywords
    if intent == "unknown":
        intent = fallback_intent_classifier(user_input)

    # 2. Named Entity Recognition (NER)
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

    # 3. Fallback Entity Extraction with Regex and Date Parsing
    try:
        src_match = re.search(r'from\s+([\w]+)', user_input, re.IGNORECASE)
        dest_match = re.search(r'to\s+([\w]+)', user_input, re.IGNORECASE)
        date_match = re.search(r'on\s+([\w\s\d]+)', user_input, re.IGNORECASE)

        if src_match and not source:
            source = src_match.group(1).upper()
        if dest_match and not destination:
            destination = dest_match.group(1).upper()
        if date_match and not date:
            parsed_date = dateparser.parse(date_match.group(1))
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print("⚠️ Regex fallback error:", str(e))

    try:
        if not date:
            parsed_date = dateparser.parse(user_input)
            if parsed_date:
                date = parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        print("⚠️ Dateparser fallback error:", str(e))

    result = {
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        }
    }

    # 5. Train Search using Indian Rail API
    if intent == "train_search" and source and destination:
        try:
            # Format: https://indianrailapi.com/api/v2/TrainBetweenStation/apikey/<APIKEY>/From/SRC/To/DST
            rail_url = f"https://indianrailapi.com/api/v2/TrainBetweenStation/apikey/{RAIL_API_KEY}/From/{source}/To/{destination}"
            result["trains"] = fetch_trains_with_retries(rail_url)
        except Exception as e:
            print("⚠️ Indian Rail API error:", str(e))
            result["trains"] = []

    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
