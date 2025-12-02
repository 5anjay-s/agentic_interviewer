# Utils (placeholder)
# services/utils.py
import re
import spacy
nlp = spacy.load("en_core_web_sm")

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(\+?\d{1,3}[\s-]?)?(\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}")

def anonymize_text(text: str) -> str:
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    doc = nlp(text)
    persons = sorted({ent.text for ent in doc.ents if ent.label_ == "PERSON"}, key=len, reverse=True)
    for p in persons:
        text = re.sub(re.escape(p), "[REDACTED_NAME]", text)
    text = re.sub(r"\b(he|she|his|her|him|hers)\b", "[REDACTED_PRONOUN]", text, flags=re.I)
    return text
