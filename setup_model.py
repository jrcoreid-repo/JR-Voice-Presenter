from pathlib import Path
from urllib.request import urlretrieve
from tempfile import TemporaryDirectory
from zipfile import ZipFile

root = Path(__file__).resolve().parent / 'models'
name = 'vosk-model-small-en-us-0.15'
if (root / name / 'am' / 'final.mdl').exists():
    print('Model already installed.')
else:
    root.mkdir(exist_ok=True)
    with TemporaryDirectory() as tmp:
        archive = Path(tmp) / 'model.zip'
        print('Downloading official Vosk English model (~40 MB)...', flush=True)
        urlretrieve('https://alphacephei.com/vosk/models/'+name+'.zip', archive)
        with ZipFile(archive) as z:
            for member in z.infolist():
                if not (root / member.filename).resolve().is_relative_to(root.resolve()):
                    raise ValueError('Unsafe archive path')
            z.extractall(root)
    print('Model installed:', root / name)
