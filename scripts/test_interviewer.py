# scripts/test_interviewer.py
import os, json, sys
from agents.interviewer_agent import generate_questions_with_tts

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python scripts/test_interviewer.py path/to/profile.json candidate_id [n_questions]")
        sys.exit(1)
    profile_path = sys.argv[1]
    cid = sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    profile = json.load(open(profile_path))
    out = generate_questions_with_tts(profile, cid, n_questions=n)
    print("Generated questions:")
    print(json.dumps(out, indent=2))
    print("\nYou should now see audio files in your GCS bucket under:", f"gs://{os.environ.get('PARSER_BUCKET')}/{cid}/questions/")
