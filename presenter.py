import argparse
import json
import queue
import time
from pathlib import Path

COMMANDS = {'slide next': 'next', 'slide back': 'back', 'slide lanjut': 'next', 'slide kembali': 'back'}

def decide(result, threshold, last, now, cooldown):
    text = result.get('text', '').strip().lower()
    words = result.get('result', [])
    if text not in COMMANDS or not words or min(w.get('conf', 0) for w in words) < threshold or now-last < cooldown:
        return None
    return COMMANDS[text]

def main():
    p = argparse.ArgumentParser(description='JR Voice Presenter v0.1')
    p.add_argument('--list-devices', action='store_true')
    p.add_argument('--device', type=int)
    p.add_argument('--model', default=str(Path(__file__).parent / 'models' / 'vosk-model-small-en-us-0.15'))
    p.add_argument('--control', action='store_true', help='Enable PowerPoint control; default is dry run')
    p.add_argument('--grammar', action='store_true', help='Experimental constrained vocabulary')
    p.add_argument('--confidence', type=float, default=.85)
    p.add_argument('--cooldown', type=float, default=1.0)
    p.add_argument('--samplerate', type=int)
    p.add_argument('--verbose', action='store_true')
    a = p.parse_args()
    import sounddevice as sd
    if a.list_devices:
        print(sd.query_devices()); return
    from vosk import Model, KaldiRecognizer, SetLogLevel
    if not Path(a.model).is_dir(): p.error('Model missing. Run setup_model.py first.')
    if not 0 <= a.confidence <= 1 or a.cooldown < 0: p.error('Invalid confidence or cooldown')
    SetLogLevel(-1)
    rate = a.samplerate or int(sd.query_devices(a.device, 'input')['default_samplerate'])
    model = Model(a.model)
    rec = KaldiRecognizer(model, rate, json.dumps(list(COMMANDS)+['[unk]'])) if a.grammar else KaldiRecognizer(model, rate)
    rec.SetWords(True)
    if a.control:
        import win32com.client
    q = queue.Queue(maxsize=40)
    overflow = False
    def callback(indata, frames, timing, status):
        nonlocal overflow
        if status: overflow = True
        try: q.put_nowait(bytes(indata))
        except queue.Full: overflow = True
    last = float('-inf')
    print(f'RUNNING | {sd.query_devices(a.device, "input")["name"]} | {rate} Hz | {"PPT CONTROL" if a.control else "DRY RUN"}', flush=True)
    print('Say: slide next / slide back. Ctrl+C to stop.', flush=True)
    try:
        with sd.RawInputStream(device=a.device, samplerate=rate, channels=1, dtype='int16', blocksize=max(1,rate//20), callback=callback):
            while True:
                try: data = q.get(timeout=1)
                except queue.Empty: continue
                if overflow:
                    overflow = False
                    rec.Reset()
                    while True:
                        try: q.get_nowait()
                        except queue.Empty: break
                    print('WARN: audio dropped; recognition reset', flush=True)
                    continue
                if not rec.AcceptWaveform(data): continue
                result = json.loads(rec.Result())
                now = time.monotonic()
                action = decide(result,a.confidence,last,now,a.cooldown)
                if a.verbose and result.get('text'): print('HEARD:',result,flush=True)
                if not action: continue
                last = now
                if not a.control:
                    print('DETECTED:',result['text'],'->',action,flush=True); continue
                try:
                    app = win32com.client.GetActiveObject('PowerPoint.Application')
                    if app.SlideShowWindows.Count != 1:
                        print('SKIP: exactly one slideshow must be running',flush=True); continue
                    view = app.SlideShowWindows(1).View
                    if action == 'next': view.Next()
                    else: view.Previous()
                    print('EXECUTED:',result['text'],flush=True)
                except Exception as exc: print('PPT ERROR:',exc,flush=True)
    except KeyboardInterrupt: print('\nSTOPPED')
    except sd.PortAudioError as exc: raise SystemExit(f'Microphone error: {exc}. Check --list-devices and restart.')

if __name__ == '__main__': main()
