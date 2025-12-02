# ADK Pipeline (placeholder)
# agents/pipeline.py
import os
import uuid
from services import parser_docai
from agents.interviewer_agent import generate_questions_with_tts

def run_pipeline_from_file(local_pdf_path: str, n_questions: int = 6):
    """
    1) Parse resume (DocumentAI) -> profile
    2) Generate questions + synthesize audio (TTS) -> uploads to GCS
    Returns dict with candidate_id and questions (list)
    """
    candidate_id = f"cand-{uuid.uuid4().hex[:8]}"
    # parser_docai.parse_resume returns artifacts and profile
    parse_out = parser_docai.parse_resume(local_pdf_path, candidate_id=candidate_id)
    profile = parse_out.get("profile", {})
    # generate questions & TTS
    questions = generate_questions_with_tts(profile, candidate_id, n_questions=n_questions)
    return {
        "candidate_id": candidate_id,
        "profile": profile,
        "questions": questions,
        "artifacts": {
            "original": parse_out.get("original"),
            "anonymized": parse_out.get("anonymized"),
            "profile_gcs": parse_out.get("profile_gcs")
        }
    }
