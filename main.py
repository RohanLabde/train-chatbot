from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# Hugging Face API setup
HF_TOKEN = os.environ.get("HF_API_TOKEN")  # set this in Render environment settings
HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}"
}

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
    return "🚆 Train Assistant is running with Hugging Face APIs!"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")

    # 1. Intent Classification via Hugging Face API
    intent_payload = {
        "inputs": user_input,
        "parameters": {"candidate_labels": INTENT_LABELS}
    }
    intent_response = requests.post(INTENT_URL, headers=HEADERS, json=intent_payload)
    intent_data = intent_response.json()
    intent = intent_data["labels"][0] if "labels" in intent_data else "unknown"

    # 2. Entity Recognition via Hugging Face API
    ner_payload = {"inputs": user_input}
    ner_response = requests.post(NER_URL, headers=HEADERS, json=ner_payload)
    ner_data = ner_response.json()

    source = destination = date = train_no = None
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

    return jsonify({
        "intent": intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        }
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
