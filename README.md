# <span style="color: #2f6b3f;">Green Man</span>

|                         |                                |
|-------------------------|--------------------------------|
|<img src="assets/greenMan.png" alt="Green Man" width="600">|Green Man is a local Linux desktop assistant that connects to a local Ollama server and helps you interact with your desktop, files, and applications through a simple graphical interface. It is designed for privacy-conscious, local-first workflows. Built-in file tools are scoped to a selected workspace. Desktop input and window actions, file writes, and shell commands require approval; desktop approvals can optionally be remembered until the app closes. |

## <span style="color: #2f6b3f;">Table of Contents</span>

- [Features](#features)
- [Architecture](#architecture)
- [Screen Shots](#screen-shots)
- [Requirements](#requirements)
  - [Wayland Requirements](#wayland-requirements)
- [Quick Start](#quick-start)
- [GNOME Wayland Window Control (optional)](#gnome-wayland-window-control-optional)
- [Microphone Dictation](#microphone-dictation)
- [Usage](#usage)
  - [Animated face](#animated-face)
  - [Performance](#performance)
- [Project Layout](#project-layout)
- [Safety and Privacy](#safety-and-privacy)
- [Testing](#testing)
- [Versioning](#versioning)
- [Contributing](#contributing)
- [Help Me Help You](#help-me-help-you)
- [License](#license)
- [Attribution](#attribution)

## <span style="color: #2f6b3f;">Features</span>

- Local chat with Ollama
- Screenshot capture for desktop inspection
- User-approved desktop control for clicks and typing
- Workspace-scoped file tools, plus user-selected image attachments
- Read, write, and inspect files within a chosen folder
- Run shell commands with explicit approval
- Optional spoken assistant responses
- Animated Green Man face that looks around, and speaks with a lip-synced mouth and expressive eyebrows, with status cues for loading, waiting, and recording (can be turned off)
- Optional spoken "Ready" after the Ollama model loads, including at startup
- Current-step highlighting for multi-line Desktop control requests
- Editable, persistent system prompt
- Support for both X11 and Wayland sessions
- Persistent local preferences for model, mode, workspace, voice setting, and face animations

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Architecture</span>

```mermaid
flowchart LR
    User[User]
    subgraph App[Green Man]
        UI[Tkinter UI]
        Face[Animated face - face.py]
        Speech[Speech player - speech.py]
        Turn[Query worker]
        Guard[Mode checks and approvals]
        Files[Workspace tools]
        Desktop[Desktop tools]
        Wayland[Wayland portal adapter]
        Status[Progress and system status]
    end
    Ollama[Local Ollama API]
    Workspace[Selected workspace]
    Portal[XDG Desktop Portal]
    PipeWire[PipeWire / GStreamer]
    Linux[Linux desktop session]

    User --> UI
    UI --> Turn
    UI --> Face
    UI --> Speech
    Speech -- audio levels --> Face
    Turn <--> Ollama
    Turn --> Guard
    Guard --> Files
    Guard --> Desktop
    Files <--> Workspace
    Desktop --> Linux
    Desktop --> Wayland
    Wayland <--> Portal
    Wayland <--> PipeWire
    Status --> UI
```

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Screen Shots</span>

![GreenMan](assets/greenMan-AppScreenshot.png)

![GreenMan](assets/greenMan-EditSystemPrompt.png)

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Requirements</span>

- Python 3.10 or newer
- Tkinter
- A local Ollama server
- A Linux graphical session
- A model with vision for image analysis; Screenshot and Desktop control also
  require tool-calling support
- Microphone dictation uses Vosk and the default English speech model (setup below)

On Ubuntu, install Tkinter for the Python interpreter you use to run Green Man
if it is not already available:

```bash
sudo apt install python3-tk
```

Qwen3-VL requires Ollama 0.12.7 or newer. Check the installed version with
`ollama --version` and update Ollama only if it is older than that; restart the
Ollama server after updating.

### <span style="color: #2f6b3f;">Wayland Requirements</span>

On Wayland, Green Man uses the XDG Desktop Portal and PipeWire. If needed, install the required packages on Ubuntu:

```bash
sudo apt install gstreamer1.0-tools gstreamer1.0-pipewire gstreamer1.0-plugins-good pipewire-bin
```

For basic spoken responses, install `espeak-ng` or Speech Dispatcher:

```bash
sudo apt install espeak-ng
# Alternatively:
sudo apt install speech-dispatcher python3-speechd
```

For more natural, local neural speech, install Piper into Green Man's virtual
environment. Run these commands from the project folder after completing the
Quick Start setup; using `python3 -m pip` outside the virtual environment may fail
on Debian/Ubuntu with an externally-managed-environment error:

```bash
.venv/bin/python -m pip install piper-tts
```

Download one or more Piper `.onnx` voice models and their matching `.onnx.json`
configuration files with Piper's downloader. For example:

```bash
mkdir -p ~/.local/share/piper-voices
.venv/bin/python -m piper.download_voices en_US-lessac-medium \
  --data-dir ~/.local/share/piper-voices
```

By default, Green Man looks for models in `~/.local/share/piper-voices/` (or
`$XDG_DATA_HOME/piper-voices`). Select **Voice Model Folder** beside the **Voice** dropdown
to choose a different folder; the selection is remembered between sessions.
The dropdown lists the folder's `.onnx` files, with **System voice** as the first
and default choice, and refreshes when opened. Changing folders resets an
unavailable selected model to **System voice**. Launch Green Man with that same
environment so it can find Piper:

```bash
.venv/bin/python app.py
```

Browse [Piper voice models](https://huggingface.co/rhasspy/piper-voices) and
check the selected voice's license before using it. Green Man does not download
voice models automatically. Install an audio player (`pw-play`, `paplay`, `aplay`,
or `ffplay`) to play the generated speech. See Piper's
[CLI documentation](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md)
for additional options.

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Quick Start</span>

```bash
git clone https://github.com/bryanspms/GreenMan.git
cd GreenMan
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull llama3.1:8b
ollama pull qwen3-vl:8b-instruct
python app.py
```

The default model is `llama3.1:8b`. Use a Qwen3-VL `-instruct` model for image
understanding and desktop control. The regular Qwen3-VL tags are thinking
variants; Ollama's API `think: false` setting does not disable their thinking.
If the 8B model is too slow, pull the smaller, typically faster 4B instruct model:

```bash
ollama pull qwen3-vl:4b-instruct
```

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">GNOME Wayland Window Control (optional)</span>

On GNOME Wayland, accessibility activation may be refused. The optional shell
extension enables reliable activation and closing by window title. Install it,
then log out and back in once:

```bash
cp -r gnome_extension/greenman-windows@greenman.local ~/.local/share/gnome-shell/extensions/
gnome-extensions enable greenman-windows@greenman.local
```

When the extension is running, Green Man uses it to close or activate the window
with the approved exact title. Without it, Green Man attempts to activate the
window through accessibility and uses a keyboard shortcut to close it. GNOME
Wayland may refuse accessibility activation, so title-based activation and
closing may not work without the extension.

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Microphone Dictation</span>

The microphone button beside the message field starts live, offline English
dictation. Click it again to stop; recognized phrases are added to the message
field as you speak. Audio is processed locally by Vosk.

Install the Python dependencies from the project folder:

```bash
.venv/bin/python -m pip install -r requirements.txt
sudo apt install libportaudio2 unzip
```

Download and extract the default small English model:

```bash
mkdir -p ~/.local/share
cd ~/.local/share
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip -q vosk-model-small-en-us-0.15.zip
rm vosk-model-small-en-us-0.15.zip
```

The app looks for the extracted model at
`~/.local/share/vosk-model-small-en-us-0.15`. Other languages can be used by
downloading a Vosk model and placing its extracted folder at that path.

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Usage</span>

1. Choose a workspace folder.
2. Select an assistant mode:
   - Questions only
   - Screenshot
   - Desktop control
   - Workspace files
   - Run command

   On Wayland, **Screenshot** requests screen-capture access only; **Desktop
   control** also requests pointer and keyboard access.

   Use **list_windows** to locate windows by application and title, including
   windows behind Green Man. Use **activate_window** to bring one forward,
   **close_named_window** to close it, and **list_applications** /
   **launch_application** to open an installed desktop app. Green Man shows the
   resolved window or app in its approval dialog before activation, closing, or
   launch. After a launch, Green Man reports the exact title of a newly opened
   window, or asks the model to use **list_windows** if none appeared.

   If a window name does not match exactly, Green Man tries a fuzzy match. It
   selects a window only when one is clearly the best match; otherwise it lists
   the closest windows so an exact title can be chosen. The approval dialog
   shows the resolved window.

   For controls inside a window, activate it first, then use a fresh screenshot
   for clicks and typing. Closing a window by title uses the GNOME Shell
   extension when it is available; otherwise Green Man attempts to activate the
   window through accessibility and sends the standard close shortcut. A close
   request checks whether the window remains in a window list, which does not
   prove that the entire application process has exited. Screenshots after visual
   clicks and typing are saved to
   `~/.cache/greenman/last-desktop-verification.jpg`; **desktop screenshots may
   contain private information.**

     ```mermaid
     flowchart TD
         A[Request to open, find, interact with, or close an app] --> B{Requested action}
         B -- Open --> C[list_applications]
         C --> D[Select installed app]
         D --> E[Approve launch in Green Man]
         E --> F[launch_application]
         F --> G[list_windows to verify]
         B -- Find, interact, or close --> H[list_windows]
         H --> I[Match application and window title]
         I --> J{Requested action}
         J -- Close --> K[Approve exact window title]
         K --> L[GNOME close request or accessibility focus and close shortcut]
         L --> M[list_windows to check whether the window remains]
         J -- Interact --> N[Approve and activate window]
         N --> O[Capture fresh screenshot]
         O --> P[Approve visual click or typing]
         P --> Q[Inspect verification screenshot]
     ```

   To ask about an image, drop one PNG, JPEG, or WebP file onto the message
   field. The image may be outside the selected workspace; it is attached to
   your next message and can be removed before sending.
3. Choose the Ollama model.
   Green Man checks the model capabilities reported by Ollama. It disables
   **Screenshot** and **Desktop control** when Ollama reports that vision or
   tool-calling support is missing. **view_image** is omitted from **Workspace
   files** when Ollama reports that the model lacks vision. If the capability
   check fails, Green Man reports the error instead of concluding that the
   model lacks those capabilities.
4. Optionally enable **Read responses aloud** and choose **System voice** or an
   installed Piper voice from the **Voice** dropdown.
5. Use **Edit system prompt…** beside the read-aloud checkbox to customize the
   instructions sent to the model. Saving applies the prompt to the current chat
   and future chats, and stores it in local preferences.
6. Send your request.

The **Ollama model** and **Local API URL** fields are at the top right, beside the
face. Green Man loads the selected model when it starts and whenever you change
it, shows "Loading ..." in the status line, and says "Ready" when it is loaded
(only if **Read responses aloud** is on). Controls are disabled while a model
loads.

The bottom of the window shows CPU temperature and utilization and GPU
utilization when available, updating continuously. Elapsed time counts
during a request and resets to 00:00 when the request finishes.

In **Desktop control** mode, a request with several lines is treated as a list of
steps. The line for the step currently being performed is highlighted in the
transcript, and the highlight clears when the task finishes. Which line is
highlighted is a best guess based on the tool the model runs (for example, a
`press_key` call for Enter matches the line "Send the Enter key"), so it can lag
by a line but never moves backwards. Single-line requests show no highlight.

The **Save as .txt** button appears in the top right of the transcript only while
the pointer is over it.

Click **View History** (beside **Edit system prompt…**) to see every request sent
during the current session, numbered and time-stamped. The history is kept in
memory only: it survives **New chat** but is cleared when Green Man closes.

To dictate, click the microphone icon to start listening, speak, then click it
again to stop. Review or edit the recognized text before sending.

Spoken responses are disabled by default. The voice selection is saved with your
local preferences. Common Markdown formatting marks and emoji are omitted from
speech without changing the displayed response. **System voice** uses
`espeak-ng`, `espeak`, or `spd-say` from Speech Dispatcher. Click **Stop speaking**
to interrupt the current response
without turning off spoken responses; closing Green Man also stops playback.
While a response is playing, use the green **Pause** button beside **Stop
speaking** to pause, then **Play** to resume. Speech Dispatcher may finish the
current sentence before pausing and requires the system `python3-speechd`
package. Green Man controls only its own Speech Dispatcher connection.

### <span style="color: #2f6b3f;">Animated face</span>

The Green Man face at the top left is drawn with Tkinter. By default he blinks and
twitches his nose now and then, and his eyes glance around while idle. While a
response is spoken aloud, he wears reading glasses, his eyes settle on the user,
his mouth opens and closes, and his eyebrows lift for emphasis. The glasses
disappear when he stops speaking.

After 60 seconds without activity in the app, Green Man blinks slowly three
times and yawns with half-closed eyes before closing them, putting on a nightcap,
and letting sleepy Z's float from his mouth. The nightcap disappears when he wakes.
Mouse or keyboard activity interrupts this sequence or wakes him. He stays
awake while loading a model, waiting for a response, recording, or speaking,
and the idle countdown restarts when those activities finish.

His eyes also show what the app is doing:

| State | Eyes |
| --- | --- |
| Model loading | Pupils move in a circle without blinking |
| Waiting for a response | Eyes turn yellow and look fully left and right |
| Microphone recording | Eyes turn red |
| Speaking | Eyes look forward behind reading glasses |
| Sleeping | Slow blinks and a yawn after a minute of inactivity, then closed eyes |

Select **Eye Guide** below the title beside Green Man to open a small window
showing examples of these states, along with idle and speaking eyes. Its
examples stop moving when animations are turned off. Close the guide with its
**Close** button or Escape before returning to the main window.

Untick **Green Man Animations** (beside **Read responses aloud**) to keep the face
still and neutral: no blinking, nose twitching, glancing, sleep animation, lip
movement, or colored eyes. The choice is saved in local preferences; it is on
by default.

With a Piper voice, the mouth follows the loudness of the generated audio, so it
matches the actual speech. With the **System voice** engines (`espeak-ng`,
`espeak`, `spd-say`) the audio is not available to analyze, so the mouth moves at
a steady rhythm instead. If the mouth seems ahead of or behind the voice, adjust
`MOUTH_SYNC_LATENCY_SECONDS` in `face.py`.

[Back to TOC](#table-of-contents)

### <span style="color: #2f6b3f;">Performance</span>

Desktop control advances one tool call per model response. Visual actions are
followed by a fresh screenshot; window launches and title-based closes are
checked with window listings. Speed depends on the model running on a GPU.
Check with `ollama ps`: the PROCESSOR column should show GPU, not `100% CPU`.
For Qwen3-VL, image requests use a 16,384-token context, and tool-call replies
that include an image are capped at 1,024 tokens to keep memory use and runaway
replies down.

On older NVIDIA cards (for example Pascal, such as a GTX 1070), a recent Ollama
may pick its CUDA 13 backend, which does not support them, and silently fall back
to CPU. Forcing the CUDA 12 backend with `OLLAMA_LLM_LIBRARY=cuda_v12` fixed this
in testing. For the snap install, set it with a systemd drop-in, because the snap
does not expose that option:

```bash
sudo systemctl edit snap.ollama.listener.service
# add:
# [Service]
# Environment=OLLAMA_LLM_LIBRARY=cuda_v12
sudo systemctl restart snap.ollama.listener.service
```

A snap update may replace the service file, so repeat this if the GPU stops being
used. Smaller models such as `qwen3-vl:4b-instruct` fit fully on an 8 GB GPU.

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Project Layout</span>

| File | Purpose |
|------|---------|
| `app.py` | Main window, Ollama chat, tools, approvals, preferences |
| `face.py` | `GreenManFace`: the animated face (eyes, mouth, eyebrows) |
| `speech.py` | `SpeechPlayer`: Piper and system speech, and lip-sync loudness analysis |
| `desktop_applications.py` | Installed application discovery and launching |
| `wayland_portal.py` | Wayland screenshot and input through the XDG portal |
| `gnome_shell_windows.py` | GNOME Shell window activation and closing |
| `window_accessibility.py` | Window listing and closing through AT-SPI |
| `test_*.py` | Unit and integration tests |

The app prompts before desktop input, window activation/closing, app launches,
file writes, and shell commands. You can choose to remember desktop-action
approval until the app closes.

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Safety and Privacy</span>

Green Man includes safeguards to keep operations transparent and controlled:

- File tools are limited to the selected workspace. Images deliberately dropped
  into the message field may come from elsewhere on the computer.
- File writes require approval
- Desktop input, window activation/closing, and app launches require approval;
  that approval can be remembered until the app closes
- Shell commands require approval
- Prompts, attached images, and desktop screenshots used in a request are sent
  to the configured Ollama instance. Green Man accepts only plain-HTTP URLs
  using `localhost`, `127.0.0.1`, or `::1`.
- Desktop verification screenshots are also saved locally at
  `~/.cache/greenman/last-desktop-verification.jpg`.

This is not a sandbox. Approved commands can still affect other parts of the system if the user explicitly allows them.

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Testing</span>

```bash
.venv/bin/python -m unittest
```

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Versioning</span>

The main window title shows the tag selected by `git describe` from the tags
reachable from the checked-out commit. Set or bump the release tag with:

```bash
git tag -a v1.0.0 -m "Version 1.0.0"
git push origin v1.0.0
```

When no tag is available, such as in a copy without Git history, the title shows `dev`.

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Contributing</span>

Contributions are welcome. Please open a pull request with a clear explanation of the change and its purpose.

[Back to TOC](#table-of-contents)

## <span style="color: #2f6b3f;">Help Me Help You</span>

Green Man is independently built and maintained, and developing it takes time—especially testing desktop integrations and keeping it reliable across Linux setups. Your support helps me continue improving the project, fixing issues, and keeping it free and local-first. If Green Man is useful to you, a contribution is greatly appreciated.


<a href="https://www.buymeacoffee.com/bryanspms" target="_blank">
  <img src= "assets/BuyMeAcoffee-qrCode.png" alt="Buy Me A Coffee" width="180">
</a>
&nbsp;&nbsp;
<a href="https://www.buymeacoffee.com/bryanspms" target="_blank">
  <img src= "assets/BuyMeAcoffee.gif" alt="Buy Me A Coffee" width="180">
</a>

[Back to TOC](#table-of-contents)

## <span style="color:#2f6b3f;">License</span>

Green Man is licensed under the [MIT License](LICENSE). Copyright (c) 2026
Bryan Price. See the license file for the full terms.

[Back to TOC](#table-of-contents)

## <span style="color:#2f6b3f;">Attribution</span>

If you build upon Green Man, attribution is appreciated:

> Based on GreenMan (github.com/bryanspms/GreenMan) by Bryan Price

[Back to TOC](#table-of-contents)