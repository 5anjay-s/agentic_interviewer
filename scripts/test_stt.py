# scripts/test_stt.py
import sys, json
from services import stt_service

if len(sys.argv) < 4:
    print("usage: python scripts/test_stt.py path/to/answer.wav candidate_id question_id")
    sys.exit(1)

wav = sys.argv[1]
cid = sys.argv[2]
qid = sys.argv[3]

audio_gs = stt_service.upload_answer_to_gcs(wav, f"{cid}/answers/{qid}.wav")
print("audio uploaded:", audio_gs)

trans = stt_service.transcribe_local_file(wav)
print("transcript:", trans)

trans_gs = stt_service.save_transcript_to_gcs(trans, f"{cid}/transcripts/{qid}.txt")
print("transcript saved:", trans_gs)

print("done")