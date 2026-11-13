#!/usr/bin/env python3
"""Generate the voiceover clips with ElevenLabs from narration.json into assets/audio/vo/.
Needs ELEVENLABS_API_KEY in the environment. Usage: make_narration.py [segment ids...]"""
import json, os, subprocess, sys, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); cfg = json.load(open(os.path.join(here, "narration.json")))
key = os.environ["ELEVENLABS_API_KEY"]; want = set(sys.argv[1:]); segs = cfg["segments"]
for i, s in enumerate(segs):
    if want and s["id"] not in want: continue
    body = {"text": s["text"], "model_id": cfg["model_id"], "voice_settings": {**cfg["voice_settings"], **s.get("voice_settings", {})}}
    if i > 0: body["previous_text"] = segs[i - 1]["text"]
    if i + 1 < len(segs): body["next_text"] = segs[i + 1]["text"]
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['voice_id']}?output_format=mp3_44100_128", data=json.dumps(body).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    out = os.path.join(here, "assets", "audio", "vo", s["id"] + ".mp3")
    try: open(out, "wb").write(urllib.request.urlopen(req, timeout=120).read())
    except urllib.error.HTTPError as e: print(s["id"], "FAILED", e.code, e.read()[:300]); continue
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out], capture_output=True, text=True).stdout.strip()
    print(s["id"], d, "s,", len(s["text"]), "chars")
