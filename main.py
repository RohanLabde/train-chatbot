from flask import Flask, request, jsonify
from transformers import pipeline
import torch

app = Flask(__name__)

# Load Hugging Face pipelines
ner_pipeline = pipeline("ner", model="dslim/bert-base-NER", grouped_entities=True)
classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

# Define candidate intents
INTENT_LABELS = [
    "train_search",
    "seat_availability",
    "book_ticket",
    "cancel_ticket",
    "train_status"
]

@app.route("/")
def home():
    return "🚆 Smart Train Assistant is running!"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")

    # Detect intent
    intent_result = classifier(user_input, INTENT_LABELS)
    top_intent = intent_result["labels"][0]

    # Extract entities
    ner_results = ner_pipeline(user_input)

    source = destination = date = train_no = train_class = None
    for ent in ner_results:
        label = ent["entity_group"]
        word = ent["word"]
        if label == "LOC":
            if not source:
                source = word
            elif not destination:
                destination = word
        elif label == "DATE":
            date = word
        elif label == "CARDINAL" and word.isdigit():
            train_no = word  # simplistic assumption

    # Build a basic response
    response = {
        "intent": top_intent,
        "entities": {
            "source": source,
            "destination": destination,
            "date": date,
            "train_no": train_no
        }
    }

    return jsonify(response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
