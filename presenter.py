import argparse
import json
import queue
import time
from pathlib import Path

ONES = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS = 'zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()

def number_words(n):
    if n < 20: return ONES[n]
    if n < 100: return TENS[n//10] + (' ' + ONES[n%10] if n%10 else '')
    return ONES[n//100] + ' hundred' + (' ' + number_words(n%100) if n%100 else '')

COMMANDS = {'slide next': 'next', 'slide back': 'back', 'slide first': 'first',
            'slide last': 'last', 'slide black': 'black', 'slide white': 'white',
            'slide show': 'show', 'slide lock': 'lock', 'slide unlock': 'unlock'}
COMMANDS.update({'slide ' + number_words(n): 'goto:' + str(n) for n in range(1, 201)})

def decide(result, threshold, last, now, cooldown):
    text = result.get('text', '').strip().lower()
    words = result.get('result', [])
    if text not in COMMANDS or not words or min(w.get('conf', 0) for w in words) < threshold or now-last < cooldown:
        return None
    return COMMANDS[text]

def select_device(sd, explicit=None, name=None):
    devices = sd.query_devices()
    hosts = sd.query_hostapis()
    if explicit is not None:
        sd.query_devices(explicit, 'input')
        return explicit
    candidates = [(i,d) for i,d in enumerate(devices) if d['max_input_channels'] > 0]
    def rank(item):
        i,d = item
        host = hosts[d['hostapi']]['name'].lower()
        return (0 if 'wasapi' in host else 1 if 'mme' in host else 2, i)
    if name:
        matches = [item for item in candidates if name.casefold() in item[1]['name'].casefold()]
        if not matches: raise ValueError('No input device matching ' + name)
        return min(matches, key=rank)[0]
    matches = [item for item in candidates if 'jbl tune125bt' in item[1]['name'].lower()]
    if matches: return min(matches, key=rank)[0]
    default = int(sd.default.device[0])
    sd.query_devices(default, 'input')
    return default

def main():
    p = argparse.ArgumentParser(description='JR Voice Presenter v0.3')
    p.add_argument('--list-devices', action='store_true')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--device', type=int)
    group.add_argument('--mic', help='Input device name substring, e.g. Realtek or JBL')
    p.add_argument('--model', default=str(Path(__file__).parent / 'models' / 'vosk-model-small-en-us-0.15'))
    p.add_argument('--control', action='store_true', help='Enable PowerPoint control; default is dry run')
    p.add_argument('--grammar', action=argparse.BooleanOptionalAction, default=True, help='Constrained vocabulary (default)')
    p.add_argument('--max-slide', type=int, default=100, choices=range(1,201), metavar='1-200')
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
    try:
        a.device = select_device(sd, a.device, a.mic)
        info = sd.query_devices(a.device, 'input')
        print(f"MIC SELECTED: {a.device} | {info['name']} | {sd.query_hostapis(info['hostapi'])['name']}", flush=True)
    except (ValueError, sd.PortAudioError, IndexError) as exc:
        p.error(f'Microphone selection failed: {exc}. Run --list-devices or omit --device.')
    rate = a.samplerate or int(sd.query_devices(a.device, 'input')['default_samplerate'])
    model = Model(a.model)
    rec = KaldiRecognizer(model, rate, json.dumps([k for k,v in COMMANDS.items() if not v.startswith('goto:') or int(v.split(':')[1]) <= a.max_slide]+['[unk]'])) if a.grammar else KaldiRecognizer(model, rate)
    rec.SetWords(True)
    if a.control:
        import win32com.client
    q = queue.Queue(maxsize=40)
    overflow = False
    def callback(indata, frames, timing, status):
        nonlocal overflow
        if status: overflow = True
        try: q.put_nowait((time.monotonic(), bytes(indata)))
        except queue.Full: overflow = True
    last = float('-inf')
    last_audio = time.monotonic()
    locked = False
    print(f'RUNNING | {sd.query_devices(a.device, "input")["name"]} | {rate} Hz | {"PPT CONTROL" if a.control else "DRY RUN"}', flush=True)
    print('Say: slide next / slide back / slide five / slide lock. Ctrl+C to stop.', flush=True)
    try:
        with sd.RawInputStream(device=a.device, samplerate=rate, channels=1, dtype='int16', blocksize=max(1,rate//20), callback=callback):
            while True:
                try: captured, data = q.get(timeout=1)
                except queue.Empty:
                    if time.monotonic() - last_audio > 3:
                        raise SystemExit('Microphone stopped sending audio. Restart to select a fresh device.')
                    continue
                last_audio = time.monotonic()
                if overflow or time.monotonic() - captured > .5:
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
                if action.startswith('goto:') and int(action.split(':')[1]) > a.max_slide: continue
                if locked and action != 'unlock': continue
                if action in ('lock', 'unlock'):
                    locked = action == 'lock'
                    last = now
                    print('LOCKED' if locked else 'UNLOCKED', flush=True)
                    continue
                last = now
                if not a.control:
                    print('DETECTED:',result['text'],'->',action,flush=True); continue
                try:
                    app = win32com.client.GetActiveObject('PowerPoint.Application')
                    if app.SlideShowWindows.Count != 1:
                        print('SKIP: exactly one slideshow must be running',flush=True); continue
                    view = app.SlideShowWindows(1).View
                    if action == 'next': view.Next()
                    elif action == 'back': view.Previous()
                    elif action == 'first': view.First()
                    elif action == 'last': view.Last()
                    elif action == 'black': view.State = 3
                    elif action == 'white': view.State = 4
                    elif action == 'show': view.State = 1
                    elif action.startswith('goto:'):
                        n = int(action.split(':')[1])
                        if not 1 <= n <= app.SlideShowWindows(1).Presentation.Slides.Count:
                            print('SKIP: slide out of range', flush=True); continue
                        view.GotoSlide(n)
                    else: continue
                    print('EXECUTED:',result['text'],flush=True)
                except Exception as exc: print('PPT ERROR:',exc,flush=True)
    except KeyboardInterrupt: print('\nSTOPPED')
    except sd.PortAudioError as exc: raise SystemExit(f'Microphone error: {exc}. Reconnect microphone and restart; device selection will refresh.')

if __name__ == '__main__': main()
