# app.py - Full FastAPI backend integrating pipeline endpoints and audio proxy
import os
import io
import uuid
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Import your existing agents/services (these must be present in your repo)
# - pipeline_agent.run_pipeline_from_file(local_pdf_path, n_questions)
# - agents.interviewer_agent.generate_questions_with_tts(profile, candidate_id, n_questions)
# - services.parser_docai.parse_resume(local_pdf_path, candidate_id)
# - services.stt_service.transcribe_local_file(local_wav_path)
# - agents.analyst_agent.analyze_and_report(candidate_id, questions, transcript, save_to_gcs)
try:
    from agents import pipeline as pipeline_agent
    from services import parser_docai, stt_service
    from agents.analyst_agent import analyze_and_report
    from services import tts_service
except Exception:
    # If imports fail, we still run but pipeline endpoints will raise descriptive errors
    pipeline_agent = None
    parser_docai = None
    stt_service = None
    analyze_and_report = None
    tts_service = None

from google.cloud import storage
import mimetypes

app = FastAPI(title="ADK Recruit Backend")

# CORS for frontend hosted separately (change origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mount static folder (if frontend build is copied to ./static)
if os.path.isdir("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

# GCS client and bucket
GCS_CLIENT = None
PARSER_BUCKET = os.environ.get("PARSER_BUCKET")
if PARSER_BUCKET:
    GCS_CLIENT = storage.Client()

def save_upload_temp(upload: UploadFile, suffix=""):
    ext = os.path.splitext(upload.filename)[1] or suffix
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    contents = upload.file.read()
    tf.write(contents)
    tf.flush()
    tf.close()
    return tf.name

@app.post("/pipeline/start")
async def pipeline_start(file: UploadFile = File(...), n_questions: int = Form(6)):
    if file.content_type not in ("application/pdf", "application/octet-stream", "application/pdf"):
        raise HTTPException(status_code=400, detail="Upload a PDF file")
    local_path = save_upload_temp(file, suffix=".pdf")
    candidate_id = f"cand-{uuid.uuid4().hex[:8]}"
    try:
        # Try using pipeline_agent if available
        if pipeline_agent and hasattr(pipeline_agent, "run_pipeline_from_file"):
            out = pipeline_agent.run_pipeline_from_file(local_path, n_questions=n_questions, candidate_id=candidate_id)
            return JSONResponse(content=out)
        # Otherwise try parser + interviewer steps directly if implemented
        if parser_docai and tts_service:
            parsed = parser_docai.parse_resume(local_path, candidate_id=candidate_id)
            profile = parsed.get("profile", {})
            questions = tts_service and []  # placeholder
            try:
                from agents.interviewer_agent import generate_questions_with_tts
                questions = generate_questions_with_tts(profile, candidate_id, n_questions=n_questions)
            except Exception as e:
                questions = []
            return JSONResponse(content={"candidate_id": candidate_id, "profile": profile, "questions": questions})
        raise HTTPException(status_code=500, detail="Pipeline agent not available on server.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload_answer")
async def upload_answer(file: UploadFile = File(...), candidate_id: str = Form(...), question_id: str = Form(...)):
    if not file:
        raise HTTPException(status_code=400, detail="Missing file")
    local_path = save_upload_temp(file, suffix=".wav")
    # call STT service to transcribe
    if stt_service and hasattr(stt_service, "transcribe_local_file"):
        try:
            transcript = stt_service.transcribe_local_file(local_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"STT failed: {e}")
    else:
        transcript = ""
    # optionally upload the answer wav to GCS for audit
    if GCS_CLIENT and PARSER_BUCKET:
        bucket = GCS_CLIENT.bucket(PARSER_BUCKET)
        gcs_path = f"{candidate_id}/answers/{question_id}.wav"
        blob = bucket.blob(gcs_path)
        try:
            blob.upload_from_filename(local_path, content_type="audio/wav")
            gcs_url = f"gs://{PARSER_BUCKET}/{gcs_path}"
        except Exception as e:
            gcs_url = None
    else:
        gcs_url = None
    return {"candidate_id": candidate_id, "question_id": question_id, "transcript": transcript, "audio_gcs": gcs_url}

@app.post("/analyze")
async def analyze(candidate_id: str = Form(...), questions_json: str = Form(...), transcript: str = Form(...)):
    try:
        import json
        questions = json.loads(questions_json) if isinstance(questions_json, str) else questions_json
    except Exception as e:
        raise HTTPException(status_code=400, detail="questions_json must be valid JSON")
    if not analyze_and_report:
        raise HTTPException(status_code=500, detail="Analyst agent not available")
    try:
        report = analyze_and_report(candidate_id, questions, transcript, save_to_gcs=True)
        return JSONResponse(content=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audio_proxy")
def audio_proxy(path: str):
    """
    Streams audio from the PARSER_BUCKET using the provided path (relative path inside bucket).
    Example: /audio_proxy?path=cand-abc123/questions/q1.wav
    """
    if not GCS_CLIENT or not PARSER_BUCKET:
        raise HTTPException(status_code=500, detail="Audio proxy not configured (PARSER_BUCKET missing)")
    try:
        bucket = GCS_CLIENT.bucket(PARSER_BUCKET)
        blob = bucket.blob(path)
        if not blob.exists():
            raise HTTPException(status_code=404, detail="Audio not found")
        data = blob.download_as_bytes()
        content_type = blob.content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
        return StreamingResponse(io.BytesIO(data), media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
