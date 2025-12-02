# services/stt_service.py
import os
import uuid
import wave
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import storage

BUCKET = os.environ.get("PARSER_BUCKET")
STT_CLIENT = speech.SpeechClient()
GCS_CLIENT = storage.Client()

def upload_answer_to_gcs(local_path: str, dest_path: str) -> str:
    if not BUCKET:
        raise RuntimeError("PARSER_BUCKET not set")
    bucket = GCS_CLIENT.bucket(BUCKET)
    blob = bucket.blob(dest_path)
    blob.upload_from_filename(local_path, content_type="audio/wav")
    return f"gs://{BUCKET}/{dest_path}"

def _get_wav_params(path: str):
    """
    Returns (sample_rate_hz, sample_width_bytes, channels, n_frames)
    """
    with wave.open(path, "rb") as wf:
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        channels = wf.getnchannels()
        n_frames = wf.getnframes()
    return sample_rate, sample_width, channels, n_frames

def transcribe_local_file(local_path: str, language_code: str = "en-US") -> str:
    """
    Transcribe a short audio file to text. Expects LINEAR16 WAV (uncompressed PCM).
    This function auto-detects sample rate from the WAV header and sets it in RecognitionConfig.
    """
    # detect WAV params
    try:
        sample_rate_hz, sample_width, channels, n_frames = _get_wav_params(local_path)
    except wave.Error as e:
        raise RuntimeError(f"File is not a readable WAV: {e}")

    # Read bytes
    with open(local_path, "rb") as f:
        content = f.read()

    audio = speech.RecognitionAudio(content=content)

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sample_rate_hz,
        language_code=language_code,
        enable_automatic_punctuation=True,
        enable_word_time_offsets=True,
    )

    response = STT_CLIENT.recognize(config=config, audio=audio)
    transcripts = []
    for result in response.results:
        transcripts.append(result.alternatives[0].transcript)
    return " ".join(transcripts)

def save_transcript_to_gcs(transcript_text: str, dest_path: str) -> str:
    if not BUCKET:
        raise RuntimeError("PARSER_BUCKET not set")
    bucket = GCS_CLIENT.bucket(BUCKET)
    blob = bucket.blob(dest_path)
    blob.upload_from_string(transcript_text, content_type="text/plain")
    return f"gs://{BUCKET}/{dest_path}"
