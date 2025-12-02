# agents/llm_utils.py
import os
import json
import re
from typing import Optional

# Try to import google-genai Client
try:
    from google.genai import Client as GenaiClient
    HAVE_GENAI = True
except Exception:
    HAVE_GENAI = False

def _extract_json_block(text: str) -> Optional[str]:
    """
    Extract first {...} block from text. Returns None if not found.
    """ 
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return None

def call_gemini_via_vertex(prompt: str, model: str = None, max_output_tokens: int = 1024, temperature: float = 0.0) -> str:
    """
    Call Gemini on Vertex using google-genai client configured for Vertex.
    Returns the raw text output from the model.
    Raises RuntimeError if google-genai is not available or call fails.
    """
    if not HAVE_GENAI:
        raise RuntimeError("google-genai client not installed (pip install google-genai).")

    project = os.environ.get("PROJECT_ID")
    location = os.environ.get("DOCAI_LOCATION", os.environ.get("GENAI_LOCATION", "us-central1"))
    model = model or os.environ.get("LLM_MODEL", "gemini-1.5-flash")

    client = GenaiClient(vertexai=True, project=project, location=location)

    # generate_content expects a list of content dicts in newer versions
    response = client.models.generate_content(
        model=model,
        contents=[{"type": "text", "text": prompt}],
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    # response.output is the recommended field; response.text sometimes present
    outputs = []
    # Try response.output
    try:
        for out in (response.output or []):
            # out may be dict-like with content list
            if isinstance(out, dict) and "content" in out:
                for c in out["content"]:
                    if isinstance(c, dict) and "text" in c:
                        outputs.append(c["text"])
            elif hasattr(out, "text"):
                outputs.append(out.text)
    except Exception:
        pass

    # fallback to response.text attribute if nothing collected
    if not outputs and hasattr(response, "text"):
        try:
            outputs.append(response.text)
        except Exception:
            pass

    result = "\n".join(outputs).strip()
    return result

def generate_json_from_llm(prompt: str, model: str = None, **kwargs) -> dict:
    """
    Call Gemini via Vertex to produce JSON output. Attempts to parse and repair common problems.
    Returns parsed JSON or raises ValueError if parsing fails.
    """
    txt = call_gemini_via_vertex(prompt, model=model, **kwargs)
    # try direct JSON parse
    try:
        return json.loads(txt)
    except Exception:
        # try extracting JSON block
        js = _extract_json_block(txt)
        if js:
            try:
                return json.loads(js)
            except Exception:
                # final attempt: clean trailing commas
                cleaned = re.sub(r",\s*}", "}", js)
                cleaned = re.sub(r",\s*]", "]", cleaned)
                try:
                    return json.loads(cleaned)
                except Exception as e:
                    raise ValueError(f"Failed to parse JSON from LLM output. last attempt error: {e}\nLLM output:\n{txt[:4000]}")
        raise ValueError(f"LLM output not valid JSON and no JSON block found. LLM output:\n{txt[:4000]}")
