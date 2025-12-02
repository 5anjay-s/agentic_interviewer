# agents/analyst_agent.py
"""
Analyst Agent
- Scores candidate answers (transcript) against questions+ideal answers.
- Primary path: calls LLM (Gemini on Vertex) via agents.llm_utils.generate_json_from_llm
- Fallback: deterministic heuristic scorer
- Saves report JSON to GCS via services.analysis_utils.upload_json_to_gcs (if save_to_gcs=True)
"""

import os
import json
import math
from typing import List, Dict, Any

from services import analysis_utils

# LLM utils provide generate_json_from_llm() and HAVE_GENAI flag
try:
    from agents.llm_utils import generate_json_from_llm, HAVE_GENAI
except Exception:
    HAVE_GENAI = False
    def generate_json_from_llm(*args, **kwargs):
        raise RuntimeError("agents.llm_utils not available")


# Default model (can be overridden with env LLM_MODEL)
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-1.5-pro")


def _build_llm_prompt(questions: List[Dict[str, Any]], transcript: str) -> str:
    schema_example = {
        "per_question": [
            {
                "id": "q1",
                "technical_accuracy": 0,
                "depth": 0,
                "communication": 0,
                "ownership": 0,
                "notes": "short justification"
            }
        ],
        "aggregate": {
            "total_score": 0,
            "max_score": 0,
            "recommendation": "HIRE|HOLD|NO_HIRE",
            "summary": "short summary justification"
        }
    }

    num_q = len(questions)
    max_score = 15 * num_q

    prompt = (
        "You are an unbiased hiring analyst.\n"
        "INPUT: A list of interview questions with 'ideal' answers and a candidate transcript containing their spoken answers.\n\n"
        "TASK: For each question, find the candidate's answer in the transcript and score it using this rubric (exact numeric ranges):\n"
        "- technical_accuracy (0-5): factual/technical correctness vs the ideal answer.\n"
        "- depth (0-5): depth, specifics, algorithms/architecture, clarity about tradeoffs.\n"
        "- communication (0-3): clarity, structure, conciseness.\n"
        "- ownership (0-2): clear personal contribution (I implemented/wrote/designed vs passive).\n\n"
        "Aggregate rules:\n"
        f"- total_score is the sum of per-question totals. max_score = {max_score}.\n"
        "- Recommendation thresholds: HIRE >= 73% of max; HOLD >= 50% and <73%; NO_HIRE < 50%.\n\n"
        "REPLY FORMAT: Return JSON only, exactly following this example schema (no extra commentary):\n"
        f"{json.dumps(schema_example, indent=2)}\n\n"
        "QUESTIONS (id, q, ideal):\n"
    )
    for q in questions:
        prompt += f"- id: {q.get('id')}\n  q: {q.get('q')}\n  ideal: {q.get('ideal')}\n\n"

    prompt += "\nTRANSCRIPT:\n" + (transcript or "")[:16000]
    prompt += "\n\nReturn JSON now."
    return prompt


def _parse_llm_response(parsed: dict, questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("LLM output is not a dict")

    if "per_question" not in parsed or "aggregate" not in parsed:
        raise ValueError("LLM output missing required keys 'per_question' or 'aggregate'")

    per_q = parsed["per_question"]
    normalized = []
    ids_seen = set()
    for item in per_q:
        qid = str(item.get("id", ""))
        ids_seen.add(qid)
        normalized.append({
            "id": qid,
            "technical_accuracy": int(item.get("technical_accuracy", 0)),
            "depth": int(item.get("depth", 0)),
            "communication": int(item.get("communication", 0)),
            "ownership": int(item.get("ownership", 0)),
            "notes": str(item.get("notes", ""))[:1000],
        })

    for q in questions:
        if q.get("id") not in ids_seen:
            normalized.append({
                "id": q.get("id"),
                "technical_accuracy": 0,
                "depth": 0,
                "communication": 0,
                "ownership": 0,
                "notes": "Missing from LLM output"
            })

    agg = parsed.get("aggregate", {})
    aggregate = {
        "total_score": int(agg.get("total_score", 0)),
        "max_score": int(agg.get("max_score", len(questions) * 15)),
        "recommendation": str(agg.get("recommendation", "")).upper(),
        "summary": str(agg.get("summary", ""))[:2000],
    }

    return {"per_question": normalized, "aggregate": aggregate}


def _fallback_score(questions: List[Dict[str, Any]], transcript: str) -> Dict[str, Any]:
    per_q = []
    total = 0
    t_lower = (transcript or "").lower()

    for q in questions:
        qid = q.get("id")
        ideal = (q.get("ideal") or "").lower()
        qtext = (q.get("q") or "").lower()

        tokens = set()
        for text in (ideal + " " + qtext).split():
            tok = text.strip(".,()\"'[]{}:;").lower()
            if len(tok) > 3:
                tokens.add(tok)

        matches = sum(1 for tok in tokens if tok in t_lower)

        technical = min(5, matches // 1)
        depth = min(5, matches // 1)
        communication = 0
        if matches >= 1:
            communication = 2
        if matches >= 4:
            communication = 3
        ownership = 1 if (" i " in t_lower or "i implemented" in t_lower or "i wrote" in t_lower or "my role" in t_lower) else 0

        q_total = technical + depth + communication + ownership
        per_q.append({
            "id": qid,
            "technical_accuracy": int(technical),
            "depth": int(depth),
            "communication": int(communication),
            "ownership": int(ownership),
            "notes": f"matches={matches}"
        })
        total += q_total

    max_score = 15 * len(questions)
    pct = (total / max_score) if max_score else 0.0
    if pct >= 0.73:
        rec = "HIRE"
    elif pct >= 0.5:
        rec = "HOLD"
    else:
        rec = "NO_HIRE"

    summary = f"Total {total}/{max_score} ({pct*100:.1f}%) -> {rec}"

    return {"per_question": per_q, "aggregate": {"total_score": total, "max_score": max_score, "recommendation": rec, "summary": summary}}


def _score_with_llm(questions: List[Dict[str, Any]], transcript: str) -> Dict[str, Any]:
    prompt = _build_llm_prompt(questions, transcript)
    try:
        parsed = generate_json_from_llm(prompt, model=os.environ.get("LLM_MODEL", LLM_MODEL), max_output_tokens=1400, temperature=0.0)
        normalized = _parse_llm_response(parsed, questions)
        return normalized
    except Exception as e:
        print("[Analyst LLM] error or invalid output, falling back to heuristic:", e)
        return _fallback_score(questions, transcript)


def analyze_and_report(candidate_id: str, questions: List[Dict[str, Any]], transcript: str, save_to_gcs: bool = True) -> Dict[str, Any]:
    scoring = _score_with_llm(questions, transcript)

    report = {
        "candidate_id": candidate_id,
        "questions_count": len(questions),
        "result": scoring,
    }

    if save_to_gcs:
        try:
            dest_path = f"{candidate_id}/reports/report.json"
            gcs_path = analysis_utils.upload_json_to_gcs(report, dest_path)
            report["gcs_path"] = gcs_path
        except Exception as e:
            print("[Analyst] warning: failed to upload report to GCS:", e)
            local_dir = os.path.join("artifacts")
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, f"{candidate_id}_report.json")
            with open(local_path, "w") as f:
                json.dump(report, f, indent=2)
            report["gcs_path"] = None
            report["local_path"] = local_path
            report["upload_error"] = str(e)

    return report


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("usage: python agents/analyst_agent.py path/to/questions.json path/to/transcript.txt candidate_id")
        sys.exit(1)

    questions = json.load(open(sys.argv[1]))
    transcript = open(sys.argv[2]).read()
    cid = sys.argv[3]

    out = analyze_and_report(cid, questions, transcript, save_to_gcs=True)
    print(json.dumps(out, indent=2))
