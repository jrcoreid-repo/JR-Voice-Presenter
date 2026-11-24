# JR Voice Presenter v0.2
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
Next/Previous use COM, including animation steps per PowerPoint behavior. No keyboard injection. If COM cannot attach, ensure PowerPoint and Python run under the same user and privilege level. Restart the app if headset disconnects; automatic reconnect is not part of v0.2.

## Tuning
Default constrained grammar + exact finalized phrase matching. Use `--no-grammar` for unrestricted recognition. Grammar can increase false positives; test realistic lecture speech. Default minimum word confidence .85, cooldown 1s. Confidence is not a calibrated probability. English only; Indonesian aliases removed. Native device sample rate is default; try `--samplerate 16000` if supported. End-of-utterance latency depends on Vosk endpoint detection; no measured latency claims yet. Model download needs internet once; runtime is offline.

## Tests
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
Unit tests cover command validation only; microphone and Windows COM require real Windows testing.

## GitHub
Create an empty repository `JR-Voice-Presenter` and upload the extracted project files including `.gitignore`, or run `git init`, `git add .`, `git commit -m "Initial v0.1 prototype"`, `git branch -M main`, `git remote add origin <your repository URL>`, `git push -u origin main`. Never commit models or virtual environments.

## V0.2 commands
`slide next`, `slide back`, `slide first`, `slide last`, `slide black`, `slide white`, `slide show`, `slide lock`, `slide unlock`, and English numbers (`slide one` through `slide one hundred` by default). Use `--max-slide 200` for larger decks (maximum 200). Numbered jumps are checked against deck size. Only one running slideshow is supported. Lock blocks actions until unlock. Audio queue blocks older than 500 ms trigger a reset; this is not an end-to-end latency guarantee. Noise suppression and automatic reconnect are not implemented yet. Test in dry run before classroom use.

## Portable Windows executable (experimental)
Run `build_windows.bat` from the repository on Windows. The script uses the existing `.venv`, installs PyInstaller, verifies the model and runs synthetic self-tests, builds a console executable, copies the model beside it and checks the packaged executable. Keep the entire `dist/JR-Voice-Presenter` directory together. Double-click the executable to enable PowerPoint control, or run `JR-Voice-Presenter.exe --verbose` for dry-run testing. `JR-Voice-Presenter.exe --control --mic Realtek` selects the internal microphone. No Python installation is required on the destination PC; desktop PowerPoint is required for control. Windows packaging and hardware tests must be verified locally. Do not commit `.venv`, `models`, `build`, or `dist`.
