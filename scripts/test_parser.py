# Test Parser (placeholder)
# scripts/test_parser.py
import sys
from services import parser_docai

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/test_parser.py samples/sample_resume.pdf [candidate_id]")
        sys.exit(1)
    path = sys.argv[1]
    cid = sys.argv[2] if len(sys.argv) > 2 else "test-cand"
    print("Parsing", path)
    out = parser_docai.parse_resume(path, cid)
    print("Result profile:", out["profile"])
    print("GCS profile at:", out["profile_gcs"])
