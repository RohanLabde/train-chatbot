from flask import Flask, request, jsonify
import spacy

app = Flask(__name__)

# Load the spaCy language model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

@app.route("/")
def home():
    return "🚆 Train Search Chatbot is running!"

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    user_input = data.get("message", "")

    doc = nlp(user_input.lower())

    source = None
    destination = None
    date = None

    for ent in doc.ents:
        if ent.label_ == "GPE":  # Geopolitical Entity — often cities/stations
            if not source:
                source = ent.text
            elif not destination:
                destination = ent.text
        elif ent.label_ == "DATE":
            date = ent.text

    if not source or not destination:
        return jsonify({"response": "Please mention both source and destination stations."})

    response = f"Searching trains from {source.title()} to {destination.title()}"
    if date:
        response += f" on {date.title()}"

    return jsonify({"response": response})
