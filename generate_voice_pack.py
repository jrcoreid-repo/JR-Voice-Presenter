"""Generate MP3 feedback clips once online. Playback can be offline."""
import argparse
import asyncio
import json
from pathlib import Path
from presenter import number_words

PHRASES = {
    'startup': 'All systems operational. Welcome back, sir.',
    'ready': 'Ready when you are, sir.',
    'next': 'Certainly, sir.',
    'back': 'As you wish, sir.',
    'first': 'Returning to the beginning.',
    'last': 'Final slide, sir.',
    'lock': 'Voice control secured.',
    'unlock': 'At your service, sir.',
    'black': 'Screen hidden.',
    'white': 'White screen.',
    'show': 'Screen restored.',
    'error': 'Unable to comply, sir.',
    'unavailable': 'Slide unavailable, sir.',
    'shutdown': 'Until next time, sir.',
    'goto': 'Navigating to the requested slide, sir.',
}

async def generate(args):
    import edge_tts
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    phrases = dict(PHRASES)
    phrases.update({f'goto_{n:03d}': f'Slide {number_words(n)}, sir.'
                    for n in range(1, args.numbers + 1)})
    failed = []
    for key, phrase in phrases.items():
        target = root / (key + '.mp3')
        temp = root / (key + '.tmp.mp3')
        if target.exists() and target.stat().st_size > 0 and not args.force:
            print('SKIP:', target.name, flush=True)
            continue
        for attempt in range(3):
            try:
                await edge_tts.Communicate(phrase, args.voice, rate=args.rate,
                                           pitch=args.pitch).save(str(temp))
                if not temp.exists() or not temp.stat().st_size:
                    raise RuntimeError('Empty audio')
                temp.replace(target)
                print('SAVED:', target.name, flush=True)
                break
            except Exception as exc:
                temp.unlink(missing_ok=True)
                print(f'WARN: {key}, attempt {attempt+1}: {exc}', flush=True)
                if attempt == 2:
                    failed.append(key)
                else:
                    await asyncio.sleep(2 ** attempt)
        await asyncio.sleep(.25)
    manifest = {'voice': args.voice, 'rate': args.rate, 'pitch': args.pitch,
                'clips': {k: {'file': k+'.mp3', 'text': v} for k,v in phrases.items()
                          if k not in failed and (root / (k+'.mp3')).exists()},
                'failed': failed}
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Finished: {len(manifest["clips"])} clips; {len(failed)} failed. Folder: {root.resolve()}')
    return bool(failed)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--voice', default='en-GB-RyanNeural')
    p.add_argument('--rate', default='-5%')
    p.add_argument('--pitch', default='-12Hz')
    p.add_argument('--numbers', type=int, choices=range(201), default=0, metavar='0-200')
    p.add_argument('--output', default=str(Path(__file__).resolve().parent / 'voice_pack'))
    p.add_argument('--force', action='store_true', help='Regenerate existing clips')
    args = p.parse_args()
    raise SystemExit(int(asyncio.run(generate(args))))

if __name__ == '__main__':
    main()
