# Parser Agent (placeholder)
# services/parser_docai.py
import os, json, re
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from services.utils import anonymize_text
try:
    import google.genai as genai
    HAVE_GENAI = True
except Exception:
    HAVE_GENAI = False

PROJECT_ID = os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("DOCAI_LOCATION", "us")
PROCESSOR_ID = os.environ.get("DOCAI_PROCESSOR_ID")
BUCKET = os.environ.get("PARSER_BUCKET")

def upload_text_to_gcs(text: str, dest_path: str):
    client = storage.Client()
    bucket = client.bucket(BUCKET)
    blob = bucket.blob(dest_path)
    blob.upload_from_string(text, content_type="text/plain")
    return f"gs://{BUCKET}/{dest_path}"

def upload_file_to_gcs(local_path: str, dest_path: str):
    client = storage.Client()
    bucket = client.bucket(BUCKET)
    blob = bucket.blob(dest_path)
    blob.upload_from_filename(local_path)
    return f"gs://{BUCKET}/{dest_path}"

def docai_process_file(local_path: str):
    client = documentai.DocumentProcessorServiceClient()
    name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)
    with open(local_path, "rb") as f:
        doc = {"content": f.read(), "mime_type": "application/pdf"}
    request = {"name": name, "raw_document": doc}
    result = client.process_document(request=request)
    document = result.document
    text = document.text or ""
    blocks = []
    for page in document.pages:
        for block in page.blocks:
            btxt=""
            for seg in block.layout.text_anchor.text_segments:
                start = int(seg.start_index or 0)
                end = int(seg.end_index or 0)
                btxt += text[start:end]
            blocks.append({"page": page.page_number, "text": btxt.strip()})
    return {"text": text, "blocks": blocks}

def call_structured_extractor(anonymized_text: str):
    schema_text = """
Output MUST be valid JSON with keys:
skills: list[str],
projects: list[{title,str, description,str, tech_stack:list[str], role:str, years:str}],
experience_years: int or null,
education: list[str],
summary: str
"""
    prompt = f"{schema_text}\nANONYMIZED_RESUME:\n{anonymized_text[:6000]}\nReturn JSON only."
    if HAVE_GENAI:
        resp = genai.create_text(model="models/text-bison-001", input=prompt)
        txt = resp.text
        # parse first JSON block
        try:
            json_part = txt[txt.find("{"):txt.rfind("}")+1]
            return json.loads(json_part)
        except Exception:
            return {"skills":[], "projects":[], "experience_years":None, "education":[], "summary":anonymized_text[:200]}
    else:
        # fallback simple extraction
        keywords = ["python","java","react","node","sql","docker","kubernetes","gcp","aws","tensorflow","pytorch"]
        skills=[kw for kw in keywords if kw in anonymized_text.lower()]
        projects=[]
        for ln in anonymized_text.splitlines():
            if "project" in ln.lower() or "worked on" in ln.lower():
                projects.append({"title":ln.strip()[:80], "description":"", "tech_stack":[], "role":"", "years":""})
        return {"skills":skills, "projects":projects, "experience_years":None, "education":[], "summary":anonymized_text[:180]}

def parse_resume(local_file_path: str, candidate_id: str):
    # 1) upload original
    orig_gcs = upload_file_to_gcs(local_file_path, f"{candidate_id}/original.pdf")
    # 2) run Document AI
    docai = docai_process_file(local_file_path)
    raw_text = docai["text"]
    # 3) anonymize
    anon = anonymize_text(raw_text)
    anon_gcs = upload_text_to_gcs(anon, f"{candidate_id}/anonymized.txt")
    # 4) extract structured fields via LLM (or fallback)
    profile = call_structured_extractor(anon)
    profile_gcs = upload_text_to_gcs(json.dumps(profile, indent=2), f"{candidate_id}/profile.json")
    return {"original": orig_gcs, "anonymized": anon_gcs, "profile_gcs": profile_gcs, "profile": profile}

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python services/parser_docai.py path/to/resume.pdf [candidate_id]")
        sys.exit(1)
    path = sys.argv[1]
    cid = sys.argv[2] if len(sys.argv) > 2 else "candidate-1"
    out = parse_resume(path, cid)
    print(out)
