import json, sys
from agents.analyst_agent import analyze_and_report

if len(sys.argv) < 4:
    print("usage: python scripts/test_analyst.py path/to/questions.json path/to/transcript.txt candidate_id")
    sys.exit(1)

questions = json.load(open(sys.argv[1]))
transcript = open(sys.argv[2]).read()
cid = sys.argv[3]

report = analyze_and_report(cid, questions, transcript, save_to_gcs=False)
print("REPORT (local):")
print(json.dumps(report, indent=2))
