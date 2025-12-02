/* Full polished React component for ADK Recruit (modern UI, loading overlay, audio record/play, proxy-aware).
   Save as frontend/src/RecruitApp.jsx
*/
import React, { useState, useRef, useEffect } from 'react';

/* Helper: convert gs:// -> /audio_proxy?path=... so the backend proxies audio */
const gsToProxy = (gcsUrl) => {
  if (!gcsUrl) return null;
  if (gcsUrl.startsWith('gs://')) {
    // remove gs://bucket/ and return encoded path
    const without = gcsUrl.replace('gs://', '');
    const parts = without.split('/');
    // first part is bucket; path is rest
    parts.shift();
    const path = parts.join('/');
    return `/audio_proxy?path=${encodeURIComponent(path)}`;
  }
  return gcsUrl;
};

/* Small inline icons */
const Icon = ({ name, className = '' }) => {
  switch (name) {
    case 'upload': return (<svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 3v12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M8 7l4-4 4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M21 21H3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>);
    case 'play': return (<svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M5 3v18l15-9L5 3z" fill="currentColor"/></svg>);
    case 'mic': return (<svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 1v11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M19 11a7 7 0 01-14 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M12 21v-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>);
    case 'check': return (<svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>);
    default: return null;
  }
};

/* WAV encoding helpers (resample to 16k mono, create WAV blob) */
function encodeWAV(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) view.setUint8(offset + i, string.charCodeAt(i));
  }
  let offset = 0;
  writeString(view, offset, 'RIFF'); offset += 4;
  view.setUint32(offset, 36 + samples.length * 2, true); offset += 4;
  writeString(view, offset, 'WAVE'); offset += 4;
  writeString(view, offset, 'fmt '); offset += 4;
  view.setUint32(offset, 16, true); offset += 4;
  view.setUint16(offset, 1, true); offset += 2;
  view.setUint16(offset, 1, true); offset += 2;
  view.setUint32(offset, sampleRate, true); offset += 4;
  view.setUint32(offset, sampleRate * 2, true); offset += 4;
  view.setUint16(offset, 2, true); offset += 2;
  view.setUint16(offset, 16, true); offset += 2;
  writeString(view, offset, 'data'); offset += 4;
  view.setUint32(offset, samples.length * 2, true); offset += 4;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: 'audio/wav' });
}
async function resample(samples, inputRate, outputRate) {
  if (inputRate === outputRate) return samples;
  const ratio = inputRate / outputRate;
  const outLength = Math.round(samples.length / ratio);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    const idx = i * ratio;
    const i0 = Math.floor(idx);
    const i1 = Math.min(i0 + 1, samples.length - 1);
    const t = idx - i0;
    out[i] = (1 - t) * samples[i0] + t * samples[i1];
  }
  return out;
}
async function convertBlobToWav(blob) {
  const arrayBuffer = await blob.arrayBuffer();
  const actx = new (window.AudioContext || window.webkitAudioContext)();
  const decoded = await actx.decodeAudioData(arrayBuffer.slice(0));
  const channelData = decoded.numberOfChannels > 1 ? (() => {
    const len = decoded.length; const out = new Float32Array(len);
    for (let c = 0; c < decoded.numberOfChannels; c++) {
      const d = decoded.getChannelData(c);
      for (let i = 0; i < len; i++) out[i] += d[i] / decoded.numberOfChannels;
    }
    return out;
  })() : decoded.getChannelData(0);
  const res = await resample(channelData, decoded.sampleRate, 16000);
  return encodeWAV(res, 16000);
}

export default function RecruitApp() {
  const [file, setFile] = useState(null);
  const [candidateId, setCandidateId] = useState(null);
  const [profile, setProfile] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [busyMsg, setBusyMsg] = useState('');
  const [errors, setErrors] = useState([]);
  const [transcripts, setTranscripts] = useState({});
  const [report, setReport] = useState(null);
  const mediaRef = useRef(null);
  const chunksRef = useRef([]);
  const [recordingFor, setRecordingFor] = useState(null);

  function pushError(e) {
    console.error(e);
    setErrors(prev => [String(e)].concat(prev).slice(0, 6));
  }

  async function uploadResume() {
    if (!file) return pushError('Select a PDF resume first.');
    setBusy(true); setBusyMsg('Uploading resume and parsing...');
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('n_questions', '6');
      const res = await fetch('/pipeline/start', { method: 'POST', body: fd });
      if (!res.ok) {
        const txt = await res.text(); throw new Error(`Pipeline error: ${res.status} ${txt}`);
      }
      const data = await res.json();
      setCandidateId(data.candidate_id);
      setProfile(data.profile || null);
      const mapped = (data.questions || []).map(q => ({ ...q, audio_url: gsToProxy(q.audio_gcs) }));
      setQuestions(mapped);
      setBusy(false); setBusyMsg('');
    } catch (e) {
      pushError(e); setBusy(false); setBusyMsg('');
    }
  }

  async function playAudio(url) {
    try {
      if (!url) throw new Error('Audio URL missing');
      const a = new Audio(url);
      await a.play();
    } catch (e) {
      pushError('Cannot play audio. Use audio proxy or make objects accessible. ' + e.message);
    }
  }

  async function startRecording(q) {
    if (!candidateId) return pushError('Upload resume first to get candidate id.');
    setRecordingFor(q.id);
    setBusyMsg('Recording... press Stop when done');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const mr = new MediaRecorder(stream);
      mediaRef.current = mr;
      mr.ondataavailable = (ev) => { if (ev.data && ev.data.size) chunksRef.current.push(ev.data); };
      mr.onstop = async () => {
        setBusy(true); setBusyMsg('Uploading answer and transcribing...');
        try {
          const blob = new Blob(chunksRef.current, { type: chunksRef.current[0]?.type || 'audio/webm' });
          const wav = await convertBlobToWav(blob);
          const fd = new FormData();
          fd.append('file', wav, `${candidateId}_${q.id}.wav`);
          fd.append('candidate_id', candidateId);
          fd.append('question_id', q.id);
          const res = await fetch('/upload_answer', { method: 'POST', body: fd });
          if (!res.ok) { const t = await res.text(); throw new Error(t || 'upload failed'); }
          const j = await res.json();
          setTranscripts(prev => ({ ...prev, [q.id]: j.transcript || '' }));
          setBusy(false); setBusyMsg('');
          setRecordingFor(null);
        } catch (err) {
          pushError(err); setBusy(false); setBusyMsg('');
          setRecordingFor(null);
        }
      };
      mr.start();
    } catch (err) { pushError('Microphone access denied or not available: ' + err.message); }
  }

  function stopRecording() {
    const mr = mediaRef.current;
    if (mr && mr.state !== 'inactive') mr.stop();
  }

  async function analyze() {
    setBusy(true); setBusyMsg('Preparing transcript & analyzing with Analyst agent...');
    try {
      const qPayload = questions.map(q => ({ id: q.id, q: q.q, ideal: q.ideal }));
      const combined = qPayload.map(q => `Q:${q.id} - ${q.q}\nA:${transcripts[q.id] || ''}`).join('\n\n');
      const fd = new FormData();
      fd.append('candidate_id', candidateId || 'local');
      fd.append('questions_json', JSON.stringify(qPayload));
      fd.append('transcript', combined);
      const res = await fetch('/analyze', { method: 'POST', body: fd });
      if (!res.ok) { const t = await res.text(); throw new Error(t || 'analyze failed'); }
      const j = await res.json();
      setReport(j);
      setBusy(false); setBusyMsg('');
    } catch (e) {
      pushError(e); setBusy(false); setBusyMsg('');
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white font-sans text-slate-900">
      <header className="max-w-6xl mx-auto p-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-indigo-600 to-violet-500 flex items-center justify-center text-white text-lg font-bold">AR</div>
          <div>
            <h1 className="text-xl font-semibold">ADK Recruit</h1>
            <div className="text-sm text-slate-500">Autonomous first-round interviewer</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button className="text-sm px-3 py-2 bg-white border rounded hover:shadow" onClick={() => { setProfile(null); setQuestions([]); setCandidateId(null); setTranscripts({}); }}>Reset</button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-6 grid grid-cols-12 gap-6">
        <section className="col-span-8 bg-white rounded-2xl p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Interview Workspace</h2>
            <div className="text-sm text-slate-500">Candidate: <span className="font-medium">{candidateId || '—'}</span></div>
          </div>

          <div className="border-2 border-dashed border-slate-200 p-4 rounded-lg mb-4">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-indigo-50 rounded"><Icon name="upload" /></div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <input id="resumeFile" type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files[0])} className="text-sm" />
                  <button onClick={uploadResume} disabled={!file || busy} className="ml-2 px-4 py-2 bg-indigo-600 text-white rounded">Upload & Start</button>
                </div>
                <div className="mt-2 text-xs text-slate-500">Upload a resume (PDF) and the system will anonymize, parse and generate tailored questions.</div>
              </div>
            </div>
          </div>

          {profile && (
            <div className="mb-4 p-4 rounded-lg bg-slate-50 border">
              <div className="text-sm text-slate-600">Anonymized Profile</div>
              <pre className="mt-2 bg-white p-3 rounded text-xs text-slate-700 max-h-40 overflow-auto">{JSON.stringify(profile, null, 2)}</pre>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium">Generated Questions</h3>
            </div>

            <div className="space-y-3">
              {questions.length === 0 && (<div className="text-sm text-slate-400">No questions yet — upload a resume to generate questions.</div>)}

              {questions.map(q => (
                <div key={q.id} className="p-3 bg-white border rounded flex gap-4 items-start">
                  <div className="w-10 text-indigo-600 font-semibold">{q.id}</div>
                  <div className="flex-1">
                    <div className="font-medium">{q.q}</div>
                    <div className="text-xs text-slate-500 mt-1">Ideal: {q.ideal}</div>
                    <div className="mt-3 flex gap-2 items-center">
                      <button className="px-3 py-1 bg-emerald-600 text-white rounded text-sm" onClick={() => playAudio(q.audio_url)}><Icon name="play" /> Play</button>
                      {!recordingFor && <button className="px-3 py-1 bg-indigo-600 text-white rounded text-sm" onClick={() => startRecording(q)}><Icon name="mic" /> Record</button>}
                      {recordingFor === q.id && <button className="px-3 py-1 bg-red-600 text-white rounded text-sm" onClick={stopRecording}>Stop</button>}
                      <div className="ml-auto text-xs text-slate-500">{transcripts[q.id] ? 'Answered' : 'Pending'}</div>
                    </div>
                    <div className="mt-2 text-xs text-slate-700 whitespace-pre-wrap">{transcripts[q.id] || ''}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 flex gap-2">
            <button onClick={analyze} disabled={busy || questions.length === 0} className="px-4 py-2 bg-violet-700 text-white rounded">Analyze & Report</button>
            <button onClick={() => navigator.clipboard.writeText(JSON.stringify({ candidateId, questions }, null, 2))} className="px-4 py-2 bg-gray-50 rounded">Copy Payload</button>
          </div>
        </section>

        <aside className="col-span-4 p-6 bg-white rounded-2xl shadow-sm">
          <div className="mb-4">
            <h4 className="text-sm font-semibold">Process Overview</h4>
            <p className="text-xs text-slate-500 mt-1">Shows what runs in the background (Document AI, TTS, STT, Analyst).</p>
          </div>

          <div className="mt-3 text-xs text-slate-500">{busy ? busyMsg : 'Idle — waiting for actions'}</div>

          <div className="mt-6">
            <h5 className="text-sm font-semibold">Errors</h5>
            <div className="mt-2 text-xs text-red-600 space-y-1">{errors.slice(0,5).map((e,i) => <div key={i}>{e}</div>)}</div>
          </div>

          {report && (
            <div className="mt-6 p-3 bg-emerald-50 rounded">
              <div className="text-sm font-semibold">Last Report</div>
              <div className="text-xs mt-2">Recommendation: <strong>{report.result.aggregate.recommendation}</strong></div>
              <pre className="mt-2 text-xs bg-white p-2 rounded max-h-48 overflow-auto">{JSON.stringify(report, null, 2)}</pre>
            </div>
          )}
        </aside>
      </main>

      {busy && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-[520px] shadow-lg">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600">⟳</div>
              <div>
                <div className="text-lg font-semibold">{busyMsg || 'Working...'}</div>
                <div className="text-sm text-slate-500 mt-1">This may take a few seconds — Document AI, TTS and STT calls run on GCP. You will be notified when each step completes.</div>
              </div>
            </div>
            <div className="mt-4 h-2 bg-slate-100 rounded overflow-hidden">
              <div className="h-2 bg-indigo-600 animate-pulse" style={{ width: '40%' }}></div>
            </div>
            <div className="mt-3 text-xs text-slate-400">Tip: If processing stalls, check the browser console for CORS or the server logs for permission issues.</div>
          </div>
        </div>
      )}

      <footer className="max-w-6xl mx-auto p-6 text-center text-xs text-slate-400">ADK Recruit • Demo build</footer>
    </div>
  );
}
