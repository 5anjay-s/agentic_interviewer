# agents/interviewer_agent.py
"""
Interviewer Agent
- Generates tailored interview questions (uses Vertex Gemini via agents.llm_utils when available)
- Falls back to a deterministic generator if LLM is unavailable or fails
- Synthesizes question audio via services.tts_service and uploads to GCS
- Returns list of {id, q, ideal, audio_gcs}
"""

import os
import json
import uuid
from typing import List, Dict

from services import tts_service

# LLM utilities (Gemini on Vertex). llm_utils handles client import/JSON-repair.
# If agents.llm_utils is missing, import will raise and this file will fail — ensure llm_utils.py exists.
from agents.llm_utils import generate_json_from_llm, HAVE_GENAI

LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-1.5-flash")


def _fallback_generate_questions(profile: Dict, n_questions: int = 6) -> List[Dict]:
    """
    Deterministic fallback question generator.
    Uses project titles first, then rotates through skill-based questions.
    """
    questions = []
    skills = profile.get("skills", [])
    projects = profile.get("projects", [])
    idx = 1

    # Create questions from projects first
    for p in projects:
        if idx > n_questions:
            break
        title = p.get("title", "Project")
        q = (
            f"Describe the architecture and your implementation for the project titled '{title}'. "
            "What were the main technical challenges and how did you solve them?"
        )
        ideal = (
            "Should include architecture, technologies used, specific responsibilities, challenges, "
            "and measurable outcomes."
        )
        questions.append({"id": f"q{idx}", "q": q, "ideal": ideal})
        idx += 1

    # Fill remaining questions from skills or generic prompts
    i = 0
    while idx <= n_questions:
        if skills:
            sk = skills[i % len(skills)]
            q = (
                f"Explain a non-trivial problem you solved using {sk}. "
                "Walk through your approach and why you chose that technology."
            )
            ideal = (
                "Expected: clear problem statement, approach, code/algorithm-level details, tradeoffs, and alternatives."
            )
        else:
            q = "Describe a challenging technical problem you solved and how you approached it."
            ideal = "Expected: context, technical steps, tradeoffs, and impact."

        questions.append({"id": f"q{idx}", "q": q, "ideal": ideal})
        idx += 1
        i += 1

    return questions


def _llm_generate_questions(profile: Dict, n_questions: int = 6) -> List[Dict]:
    """
    Use Vertex Gemini (via agents.llm_utils) to generate JSON of questions.
    Falls back to the deterministic generator on any failure.
    Expected LLM JSON:
    { "questions": [ {"id":"q1", "q":"...", "ideal":"..."}, ... ] }
    """
    snippet = {
        "summary": profile.get("summary", "")[:4000],
        "skills": profile.get("skills", []),
        "projects": profile.get("projects", [])[:6],
    }

    system = (
        "You are an interview question generator. Input: an anonymized candidate profile. "
        "Output: valid JSON only with key 'questions' containing a list of objects with keys: "
        "id (string), q (question string), ideal (ideal answer string). "
        f"Generate exactly {n_questions} technical questions tailored to the candidate's projects and skills."
    )

    prompt = system + "\n\nCandidateProfile:\n" + json.dumps(snippet, indent=2)

    if HAVE_GENAI:
        try:
            parsed = generate_json_from_llm(prompt, model=LLM_MODEL, max_output_tokens=800)
            qs = parsed.get("questions")
            if isinstance(qs, list) and len(qs) >= 1:
                # normalize IDs and truncate if LLM returned more
                for i, q in enumerate(qs):
                    if "id" not in q:
                        q["id"] = f"q{i+1}"
                return qs[:n_questions]
        except Exception as e:
            # LLM path failed — fall back gracefully
            print("[Interviewer LLM] falling back due to error:", e)

    # fallback deterministic generator
    return _fallback_generate_questions(profile, n_questions)


def generate_questions_with_tts(profile: Dict, candidate_id: str, n_questions: int = 6) -> List[Dict]:
    """
    Main entrypoint.
    - Generates question list (id, q, ideal)
    - Synthesizes each question to GCS via tts_service
    - Returns list of question dicts with fields: id, q, ideal, audio_gcs
    """
    questions = _llm_generate_questions(profile, n_questions=n_questions)
    result: List[Dict] = []

    for qd in questions:
        qid = qd.get("id") or f"q{uuid.uuid4().hex[:6]}"
        qtext = qd.get("q", "")
        ideal = qd.get("ideal", "")

        # Destination path in GCS: <candidate_id>/questions/<qid>.wav
        gcs_path = f"{candidate_id}/questions/{qid}.wav"

        # Synthesize and upload; tts_service raises if PARSER_BUCKET not set
        gcs_url = tts_service.synthesize_text_to_gcs(qtext, gcs_path)

        result.append({"id": qid, "q": qtext, "ideal": ideal, "audio_gcs": gcs_url})

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: python agents/interviewer_agent.py path/to/profile.json candidate_id [n_questions]")
        sys.exit(1)

    profile = json.load(open(sys.argv[1]))
    cid = sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6

    out = generate_questions_with_tts(profile, cid, n_questions=n)
    print(json.dumps(out, indent=2))
