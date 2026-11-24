# JR Voice Presenter v0.1
Offline PowerPoint voice controller — terminal prototype for Windows 10/11, Python 3.11 x64 recommended.

## Setup (PowerShell)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_model.py
.\.venv\Scripts\python.exe presenter.py --list-devices
```
Select the headset microphone (input device, not stereo output). Set Windows microphone privacy access for desktop apps. Use the actual device ID in place of 3 below.

## Test without moving slides
```powershell
.\.venv\Scripts\python.exe presenter.py --device 3 --verbose
```
Say `slide next` or `slide back`, with a short pause after each phrase. Check DETECTED and HEARD logs. Ordinary speech should not trigger actions; test realistic lecture sentences. Ctrl+C stops. No audio saved. Verbose text printed only locally.

## Live PowerPoint test
Open desktop PowerPoint, start exactly one slideshow (F5), then run:
```powershell
.\.venv\Scripts\python.exe presenter.py --device 3 --control
```
Next/Previous use COM, including animation steps per PowerPoint behavior. No keyboard injection. If COM cannot attach, ensure PowerPoint and Python run under the same user and privilege level. Restart the app if headset disconnects; automatic reconnect is not part of v0.1.

## Tuning
Default unrestricted recognition + exact finalized phrase matching helps reject unrelated lecture speech. Experimental `--grammar` restricts vocabulary but can increase false positives; compare in dry run. Default minimum word confidence .85, cooldown 1s. Confidence is not a calibrated probability. English model is the baseline; Indonesian aliases are mapped but recognition is experimental, especially if words are absent from its vocabulary. Do not assume mixed language works. Native device sample rate is default; try `--samplerate 16000` if supported. End-of-utterance latency depends on Vosk endpoint detection; no measured latency claims yet. Model download needs internet once; runtime is offline.

## Tests
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
Unit tests cover command validation only; microphone and Windows COM require real Windows testing.

## GitHub
Create an empty repository `JR-Voice-Presenter` and upload the extracted project files including `.gitignore`, or run `git init`, `git add .`, `git commit -m "Initial v0.1 prototype"`, `git branch -M main`, `git remote add origin <your repository URL>`, `git push -u origin main`. Never commit models or virtual environments.
