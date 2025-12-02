# Text-to-Speech Service (placeholder)
# services/tts_service.py
import os
from google.cloud import texttospeech
from google.cloud import storage
import uuid

TTS_CLIENT = texttospeech.TextToSpeechClient()
GCS_CLIENT = storage.Client()
BUCKET = os.environ.get("PARSER_BUCKET")  # must be set

def synthesize_text_to_wav_file(text: str, out_local_path: str):
    """
    Synthesize text -> local WAV (LINEAR16).
    """
    input_text = texttospeech.SynthesisInput(text=text)
    # neutral voice; change language_code/voice name if you want
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16)
    response = TTS_CLIENT.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
    with open(out_local_path, "wb") as f:
        f.write(response.audio_content)
    return out_local_path

def synthesize_text_to_gcs(text: str, gcs_dest_path: str):
    """
    Synthesize text -> local tmp WAV -> upload to GCS path (e.g. 'cand-1/questions/q1.wav').
    Returns full gs:// url.
    """
    tmp_name = f"/tmp/tts_{uuid.uuid4().hex}.wav"
    synthesize_text_to_wav_file(text, tmp_name)
    bucket_name = BUCKET
    if not bucket_name:
        raise RuntimeError("PARSER_BUCKET env var not set")
    bucket = GCS_CLIENT.bucket(bucket_name)
    blob = bucket.blob(gcs_dest_path)
    blob.upload_from_filename(tmp_name, content_type="audio/wav")
    return f"gs://{bucket_name}/{gcs_dest_path}"
