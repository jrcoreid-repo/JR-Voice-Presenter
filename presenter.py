import argparse
import sys
import math
from array import array
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

def confidence_reason(result, wake_threshold, command_threshold):
    words = result.get('result', [])
    if not words: return 'missing word confidence'
    if words[0].get('conf', 0) < wake_threshold: return 'wake confidence'
    if any(w.get('conf', 0) < command_threshold for w in words[1:]): return 'command confidence'
    return None

def decide_wake(result, wake_threshold, command_threshold, last, now, cooldown):
    if now-last < cooldown or confidence_reason(result, wake_threshold, command_threshold):
        return None
    return COMMANDS.get(result.get('text', '').strip().lower())

def validate_phrase(result, strict=True):
    text = result.get('text', '').strip().lower()
    words = result.get('result', [])
    if text not in COMMANDS: return 'not a command'
    if not words or ' '.join(w.get('word', '') for w in words) != text:
        return 'word mismatch'
    if not strict: return None
    try:
        spans = [(float(w['start']), float(w['end'])) for w in words]
        if any(not math.isfinite(v) for pair in spans for v in pair):
            return 'invalid timing'
        if any(not .06 <= end-start <= 2.0 for start,end in spans):
            return 'word duration'
        if not .24 <= spans[-1][1]-spans[0][0] <= 5.0:
            return 'phrase duration'
        if any(b[0]-a[1] > .8 or b[0]-a[1] < -.15 for a,b in zip(spans,spans[1:])):
            return 'word spacing'
    except (KeyError, TypeError, ValueError):
        return 'missing timing'
    return None

def wake_phrase(result, partial=False, armed=False):
    """Extract only a complete command suffix after an explicit wake word."""
    words = result.get('partial_result' if partial else 'result', [])
    tokens = [w.get('word', '') for w in words]
    if not tokens: return None
    for i in range(len(tokens)-1, -1, -1):
        size = 1 if tokens[i] == 'powerpoint' else (2 if tokens[i:i+2] == ['power', 'point'] else 0)
        if not size: continue
        tail = words[i+size:]
        if not tail: return None
        wake = dict(words[i])
        wake['word'] = 'slide'
        wake['end'] = words[i+size-1].get('end', 0)
        wake['conf'] = min(w.get('conf', 0) for w in words[i:i+size])
        normalized = [wake] + tail
        text = ' '.join(w.get('word', '') for w in normalized)
        return {'text': text, 'result': normalized} if text in COMMANDS else None
    if armed and not partial:
        first = words[0]
        synthetic = {'word':'slide', 'start':first.get('start',0)-.3,
                     'end':first.get('start',0), 'conf':1.0}
        text = 'slide ' + ' '.join(tokens)
        return {'text':text, 'result':[synthetic]+words} if text in COMMANDS else None
    return None

def wake_only(result, threshold):
    words = result.get('result', [])
    tokens = [w.get('word','') for w in words]
    size = 1 if tokens[-1:] == ['powerpoint'] else (2 if tokens[-2:] == ['power','point'] else 0)
    return bool(size and all(w.get('conf',0) >= threshold for w in words[-size:]))

def wake_grammar(limit, navigation_only=False):
    tails = [k[6:] for k,v in COMMANDS.items()
             if not v.startswith('goto:') or int(v.split(':')[1]) <= limit]
    if navigation_only:
        tails = [t for t in tails if t in ('next','back','first','last','lock','unlock','black','white','show')]
    return ['[unk]', 'powerpoint', 'power point'] + tails + [
        prefix + ' ' + tail for prefix in ('powerpoint','power point') for tail in tails]

def rms_dbfs(data):
    samples = array('h', data)
    if not samples: return -120.0
    rms = math.sqrt(sum(v*v for v in samples)/len(samples))
    return 20*math.log10(max(rms, .033)/32768)

def self_test():
    def sample(text):
        return {'text': text, 'result': [{'word': w, 'conf': .99, 'start': i*.4, 'end': i*.4+.35} for i,w in enumerate(text.split())]}
    cases = [('slide next', True), ('slide back', True), ('slide twenty five', True),
             ('slide lock', True), ('slide unlock', True), ('slide close', False),
             ('slide [unk]', False), ('[unk]', False), ('next', False),
             ('please slide next', False)]
    for phrase, expected in cases:
        result = sample(phrase)
        actual = validate_phrase(result) is None and decide(result,.85,-100,10,1) is not None
        if actual != expected: raise AssertionError(phrase)
        print('PASS:', phrase, '->', 'accept' if actual else 'reject')
    result = sample('slide next')
    result['result'][1]['start'] = 2
    result['result'][1]['end'] = 2.4
    assert validate_phrase(result) == 'word spacing'
    result = sample('slide next')
    result['result'][1]['conf'] = .4
    assert decide(result,.85,-100,10,1) is None
    assert decide(sample('slide next'),.85,9.5,10,1) is None
    print('PASS: timing, confidence and cooldown guards')
    assert wake_phrase(sample('ordinary words power point next'))['text'] == 'slide next'
    assert wake_phrase(sample('ordinary words powerpoint twenty five'))['text'] == 'slide twenty five'
    assert wake_phrase(sample('ordinary words next')) is None
    assert wake_phrase(sample('power point close')) is None
    assert wake_phrase(sample('five'), armed=True)['text'] == 'slide five'
    assert wake_only(sample('ordinary words power point'), .85)
    result = wake_phrase(sample('power point next'))
    result['result'][0]['conf'] = .756585
    assert decide_wake(result,.70,.85,-100,10,1) == 'next'
    assert decide_wake(result,.80,.85,-100,10,1) is None
    result['result'][1]['conf'] = .84
    assert decide_wake(result,.70,.85,-100,10,1) is None
    result = wake_phrase(sample('power point next'))
    result['result'][0]['conf'] = .571695
    assert decide_wake(result,.55,.85,-100,10,1) == 'next'
    assert 'power point next' in wake_grammar(100, True)
    assert 'power point eighty' not in wake_grammar(100, True)
    print('PASS: separate wake and command confidence thresholds')
    print('PASS: wake phrase suffix and separate command guards')
    print('Self-test checks synthetic results only; no audio or PowerPoint tested.')

def device_candidates(sd, explicit=None, name=None, fallback=True):
    devices = sd.query_devices()
    hosts = sd.query_hostapis()
    if explicit is not None:
        sd.query_devices(explicit, 'input')
        return [explicit]
    candidates = [(i,d) for i,d in enumerate(devices) if d['max_input_channels'] > 0]
    def rank(item):
        i,d = item
        host = hosts[d['hostapi']]['name'].lower()
        return (0 if 'wasapi' in host else 1 if 'mme' in host else 2 if 'directsound' in host else 3, i)
    def is_internal(d):
        n = d['name'].lower()
        return ('microphone' in n or 'mic input' in n) and 'realtek' in n
    preferred = [item for item in candidates if (name or 'jbl tune125bt').casefold() in item[1]['name'].casefold()]
    internal = [item for item in candidates if is_internal(item[1])]
    order = [i for i,d in sorted(preferred, key=rank)]
    if fallback and (not name or 'jbl' in name.casefold()):
        order += [i for i,d in sorted(internal, key=rank)]
    if not name and (fallback or not preferred):
        default = int(sd.default.device[0])
        if any(i == default for i,d in candidates):
            order.append(default)
    return list(dict.fromkeys(order))

class AudioLost(Exception):
    pass

def main():
    p = argparse.ArgumentParser(description='JR Voice Presenter v0.6.2 experimental')
    p.add_argument('--list-devices', action='store_true')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--device', type=int)
    group.add_argument('--mic', help='Input device name substring, e.g. Realtek or JBL')
    p.add_argument('--no-fallback', action='store_true', help='Do not switch to internal microphone after JBL failure')
    p.add_argument('--model', default=str((Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent) / 'models' / 'vosk-model-small-en-us-0.15'))
    p.add_argument('--control', action='store_true', help='Enable PowerPoint control; default is dry run')
    p.add_argument('--grammar', action=argparse.BooleanOptionalAction, default=True, help='Constrained vocabulary (default)')
    p.add_argument('--max-slide', type=int, default=100, choices=range(1,201), metavar='1-200')
    p.add_argument('--confidence', type=float, default=.85)
    p.add_argument('--wake-confidence', type=float, default=.55, help='Separate wake phrase confidence threshold')
    p.add_argument('--cooldown', type=float, default=1.0)
    p.add_argument('--samplerate', type=int)
    p.add_argument('--verbose', action='store_true')
    p.add_argument('--wake', choices=['powerpoint','legacy'], default='powerpoint')
    p.add_argument('--navigation-only', action='store_true', help='Narrow wake grammar to navigation and lock commands; no slide numbers')
    p.add_argument('--final-only', action='store_true', help='Disable experimental partial-result execution')
    p.add_argument('--self-test', action='store_true', help='Run synthetic command guard tests')
    p.add_argument('--diagnostic', action='store_true', help='Show input level and rejection reasons')
    p.add_argument('--no-timing-guard', action='store_true', help='Disable experimental duration checks for A/B tests')
    a = p.parse_args()
    if getattr(sys, 'frozen', False) and len(sys.argv) == 1:
        a.control = True
    if a.self_test:
        self_test(); return
    import sounddevice as sd
    if a.list_devices:
        print(sd.query_devices()); return
    from vosk import Model, KaldiRecognizer, SetLogLevel
    if not Path(a.model).is_dir(): p.error('Model missing. Run setup_model.py first.')
    if not 0 <= a.confidence <= 1 or not 0 <= a.wake_confidence <= 1 or a.cooldown < 0: p.error('Invalid confidence or cooldown')
    SetLogLevel(-1)
    try:
        candidates = device_candidates(sd, a.device, a.mic, not a.no_fallback)
    except (ValueError, sd.PortAudioError, IndexError) as exc:
        p.error(f'Microphone selection failed: {exc}')
    if not candidates: p.error('No matching input microphone. Run --list-devices.')
    model = Model(a.model)
    if a.control:
        import win32com.client
    last = float('-inf')
    locked = False
    try:
        for device in candidates:
            try:
                info = sd.query_devices(device, 'input')
                rate = a.samplerate or int(info['default_samplerate'])
                print(f"TRY MIC: {device} | {info['name']} | {sd.query_hostapis(info['hostapi'])['name']}", flush=True)
                grammar = wake_grammar(a.max_slide, a.navigation_only) if a.wake == 'powerpoint' else [k for k,v in COMMANDS.items() if not v.startswith('goto:') or int(v.split(':')[1]) <= a.max_slide]+['[unk]']
                rec = KaldiRecognizer(model, rate, json.dumps(grammar)) if a.grammar else KaldiRecognizer(model, rate)
                rec.SetWords(True)
                partial_enabled = a.wake == 'powerpoint' and not a.final_only and hasattr(rec, 'SetPartialWords')
                if partial_enabled: rec.SetPartialWords(True)
                armed_until = 0.0
                pending = None
                pending_since = 0.0
                consumed = False
                previous_partial = ''
                q = queue.Queue(maxsize=40)
                overflow = False
                def callback(indata, frames, timing, status):
                    nonlocal overflow
                    if status: overflow = True
                    try: q.put_nowait((time.monotonic(), bytes(indata)))
                    except queue.Full: overflow = True
                last_audio = time.monotonic()
                print('Say: PowerPoint next / back / five. Ctrl+C to stop.' if a.wake == 'powerpoint' else 'Say: slide next / back / five. Ctrl+C to stop.', flush=True)
                with sd.RawInputStream(device=device, samplerate=rate, channels=1, dtype='int16', blocksize=max(1,rate//20), callback=callback):
                        print(f'RUNNING | {info["name"]} | {rate} Hz | {"PPT CONTROL" if a.control else "DRY RUN"}', flush=True)
                        last_audio = time.monotonic()
                        warmup_until = last_audio + .5
                        next_meter = last_audio + 1
                        peak_level = -120.0
                        last = max(last, last_audio)
                        while True:
                            try: captured, data = q.get(timeout=1)
                            except queue.Empty:
                                if time.monotonic() - last_audio > 3:
                                    raise AudioLost('Microphone stopped sending audio')
                                continue
                            last_audio = time.monotonic()
                            if captured < warmup_until: continue
                            if overflow or time.monotonic() - captured > .5:
                                overflow = False
                                rec.Reset()
                                armed_until = 0.0
                                pending = None
                                consumed = False
                                while True:
                                    try: q.get_nowait()
                                    except queue.Empty: break
                                print('WARN: audio dropped; recognition reset', flush=True)
                                continue
                            if a.diagnostic:
                                peak_level = max(peak_level, rms_dbfs(data))
                                if last_audio >= next_meter:
                                    print(f'INPUT peak block RMS: {peak_level:.1f} dBFS', flush=True)
                                    peak_level = -120.0
                                    next_meter = last_audio + 1
                            final = rec.AcceptWaveform(data)
                            now = time.monotonic()
                            if not final and not partial_enabled: continue
                            raw = json.loads(rec.Result() if final else rec.PartialResult())
                            if not final and a.verbose and raw.get('partial') != previous_partial:
                                previous_partial = raw.get('partial', '')
                                if previous_partial: print('PARTIAL:', previous_partial, flush=True)
                            if final: previous_partial = ''
                            if a.verbose and final and raw.get('text'):
                                print('RAW:', raw, flush=True)
                            if a.wake == 'powerpoint':
                                if consumed:
                                    if final:
                                        consumed = False
                                        pending = None
                                    continue
                                result = wake_phrase(raw, not final, now <= armed_until)
                                if final:
                                    pending = None
                                    if result is None and wake_only(raw, a.wake_confidence):
                                        armed_until = now + 3.0
                                        print('ARMED | say command within 3 seconds', flush=True)
                                        continue
                                    armed_until = 0.0
                                else:
                                    # Do not execute number prefixes (five vs fifty, twenty vs twenty five).
                                    if result is None or COMMANDS[result['text']].startswith('goto:'):
                                        pending = None
                                        continue
                                    key = result['text']
                                    if pending != key:
                                        pending = key
                                        pending_since = now
                                        continue
                                    if now-pending_since < .35: continue
                                if result is None:
                                    if final and a.verbose and raw.get('text'): print('IGNORED:', raw['text'], flush=True)
                                    continue
                            else:
                                result = raw
                            action = decide_wake(result,a.wake_confidence,a.confidence,last,now,a.cooldown) if a.wake == 'powerpoint' else decide(result,a.confidence,last,now,a.cooldown)
                            if a.verbose and result.get('text'): print('MATCH:',result,flush=True)
                            reason = validate_phrase(result, not a.no_timing_guard)
                            if reason or not action:
                                if (a.verbose or a.diagnostic) and result.get('text') and final:
                                    print('REJECT:', reason or confidence_reason(result, a.wake_confidence if a.wake == 'powerpoint' else a.confidence, a.confidence) or 'cooldown', flush=True)
                                continue
                            if action.startswith('goto:') and (int(action.split(':')[1]) > a.max_slide or (a.wake == 'powerpoint' and a.navigation_only)): continue
                            if locked and action != 'unlock':
                                if a.diagnostic: print('REJECT: locked', flush=True)
                                continue
                            if action in ('lock', 'unlock'):
                                locked = action == 'lock'
                                if not final:
                                    rec.Reset()
                                    pending = None
                                    armed_until = 0.0
                                    previous_partial = ''
                                last = now
                                print('LOCKED' if locked else 'UNLOCKED', flush=True)
                                continue
                            last = now
                            if not final:
                                rec.Reset()
                                pending = None
                                armed_until = 0.0
                                previous_partial = ''
                            if not a.control:
                                print('DETECTED:',result['text'].replace('slide ', 'PowerPoint ', 1) if a.wake == 'powerpoint' else result['text'],'->',action,flush=True); continue
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
                                print('EXECUTED:',result['text'].replace('slide ', 'PowerPoint ', 1) if a.wake == 'powerpoint' else result['text'],flush=True)
                            except Exception as exc: print('PPT ERROR:',exc,flush=True)
            except (sd.PortAudioError, AudioLost, ValueError) as exc:
                print(f'WARN: microphone {device} failed: {exc}; trying next input', flush=True)
        print('PAUSED: no usable microphone. Reconnect and restart; no commands executed.', flush=True)
    except KeyboardInterrupt:
        print('\nSTOPPED')

if __name__ == '__main__': main()
