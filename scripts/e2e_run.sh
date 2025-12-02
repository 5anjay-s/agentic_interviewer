# scripts/e2e_run.sh
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH=$PWD
# ensure envs are set in your shell - script assumes they are exported already

# Inputs
RESUME="samples/sample_resume.pdf"
NQ=4               # number of questions to request (keeps test quick)
OUT="pipeline_response.json"
CAND_DIR_TMP="/tmp/adk_e2e"   # local temp folder for audio/transcripts
mkdir -p "$CAND_DIR_TMP"

echo "1) POST /pipeline/start -> create candidate and generate questions (TTS)."
curl -s -X POST "http://127.0.0.1:8080/pipeline/start" \
  -F "file=@${RESUME}" \
  -F "n_questions=${NQ}" \
  -o "$OUT"

if [ ! -s "$OUT" ]; then
  echo "ERROR: pipeline didn't return response. Check server logs."
  exit 2
fi

cat "$OUT" | jq .

CAND_ID=$(jq -r '.candidate_id' "$OUT")
echo "Candidate ID: $CAND_ID"

echo "2) Download question audio files from GCS (audio_gcs fields)."
mkdir -p "$CAND_DIR_TMP/$CAND_ID/questions"
jq -r '.questions[] | .audio_gcs' "$OUT" | while read -r g; do
  fname=$(basename "$g")
  echo "Downloading $g -> $CAND_DIR_TMP/$CAND_ID/questions/$fname"
  gsutil cp "$g" "$CAND_DIR_TMP/$CAND_ID/questions/$fname"
done

echo "3) Simulate candidate answers by re-using question audio (fast test). Upload answers to /upload_answer"
TRANSCRIPTS_FILE="$CAND_DIR_TMP/$CAND_ID/transcripts_all.txt"
> "$TRANSCRIPTS_FILE"

i=1
for wav in "$CAND_DIR_TMP/$CAND_ID/questions"/*.wav; do
  qid="q${i}"
  echo "Uploading simulated answer for $qid: $wav"
  # use curl to POST wav to FastAPI endpoint
  RESP=$(curl -s -X POST "http://127.0.0.1:8080/upload_answer" \
    -F "file=@${wav};type=audio/wav" \
    -F "candidate_id=${CAND_ID}" \
    -F "question_id=${qid}")
  echo "upload_answer response: $RESP"
  # extract transcript and append to transcripts_all
  T=$(echo "$RESP" | jq -r '.transcript // empty')
  echo "=== $qid ===" >> "$TRANSCRIPTS_FILE"
  echo "$T" >> "$TRANSCRIPTS_FILE"
  ((i++))
done

echo "Transcripts aggregated at $TRANSCRIPTS_FILE"
cat "$TRANSCRIPTS_FILE"

echo "4) Build questions JSON for analysis (id,q,ideal)"
QUEST_JSON="$CAND_DIR_TMP/$CAND_ID/questions_payload.json"
jq '[.questions[] | {id: .id, q: .q, ideal: .ideal}]' "$OUT" > "$QUEST_JSON"
echo "Questions saved to $QUEST_JSON"

echo "5) Call /analyze with transcripts (POST form)."
TRANSCRIPT_STR=$(python - <<PY
import sys
print(open("$TRANSCRIPTS_FILE").read().strip().replace('\n','\\n'))
PY
)

# POST to /analyze (form fields)
ANALYZE_RESP=$(curl -s -X POST "http://127.0.0.1:8080/analyze" \
  -F "candidate_id=${CAND_ID}" \
  -F "questions_json=$(cat $QUEST_JSON | sed 's/"/\\"/g')" \
  -F "transcript=${TRANSCRIPT_STR}")

echo "ANALYZE response:"
echo "$ANALYZE_RESP" | jq .

echo "6) Done. report saved in GCS or local artifacts (check output above)."
