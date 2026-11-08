# camDetection 👁️

**Live object detection from a camera.**
Point a camera at something and the program draws a box around each object it recognises
(e.g. *person*, *car*, *cow*, *cell phone*) and shows it live in a password-protected web page.
When a chosen object appears it can **flash it red, say it out loud, and send a photo +
5-second video to your Telegram**. You can also control it from Telegram (`/photo`, `/status`, …).

Built with Python, [OpenCV](https://opencv.org/) and [YOLO (Ultralytics)](https://docs.ultralytics.com/).

---

## ✨ Features

- 🎥 **Live detection** of 80 common objects, or **600 objects** with the larger model
- 🌐 **Web dashboard**: watch the camera from a browser on your computer or phone, with live counts,
  recent activity, and settings you can change while it runs
- 📲 **Telegram alerts** with a photo **and a 5-second video** when chosen objects appear
- 🤖 **Telegram bot commands**: `/photo`, `/status`, `/on`, `/off`, `/camera`, `/voice`, `/help`
- 🔊 **Voice alert**: the computer says *"Alert! Teddy bear detected."* out loud
- 🎛️ **Alerts panel** in the web page: switch Telegram / video / voice on and off and choose
  the alert objects while it runs
- 🔐 **Login page** so only you can open the camera page
- 🚨 **Flashing red box** around alert objects so they stand out on screen
- 🎥 **Camera picker** with a preview of every camera, plus a one-tap **Switch camera** button
- 📸 Snapshots, adjustable confidence and text size

---

## 📋 Requirements

- macOS or 64-bit Windows 10/11
- Python 3.10 or newer
- A camera: built-in webcam, USB webcam, iPhone (Continuity Camera) or an IP/CCTV stream
- Internet on first run (to download the detection model) and for Telegram

---

## 🛠️ Installation (one time)

### macOS

Open Terminal in the project folder and run:

```bash
cd /Applications/Sites/camDetection
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> Every time you open a **new** terminal, activate the environment again with
> `source .venv/bin/activate`. You will see `(.venv)` at the start of the line.
>
> **Getting `command not found: python`?** The environment is not active. Either run
> `source .venv/bin/activate` first, or use the full path instead of `python`:
> `.venv/bin/python web_app.py`. This always works.

> **About the commands in this README:** the grey boxes show what to type in the terminal.
> Type only the command inside (e.g. `python web_app.py`) and press **Enter**. Don't type
> the ```` ``` ```` marks.

### Windows 10/11

Install 64-bit Python 3.12, open **PowerShell** in the project folder, and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks `Activate.ps1`, either run the app directly with
`.\.venv\Scripts\python.exe web_app.py`, or allow locally-created scripts for your account:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Do not copy the `.venv` folder from a Mac. Virtual environments are specific to the computer
and operating system that created them.

---

## 🚀 Start the server

The **server** is `web_app.py`. It runs the camera + detection, serves the web page and
listens for Telegram commands. It only works **while the terminal stays open**.

### 1. Open a terminal in the project folder

```bash
cd /Applications/Sites/camDetection
```

On Windows, open the folder in PowerShell instead, for example:

```powershell
cd C:\Projects\camDetection
```

### 2. Start it (pick one)

| What you want | Command |
|---|---|
| Web page on this computer only | `python web_app.py` |
| Web page on computer **and phone** (same Wi-Fi) | `python web_app.py --phone` |
| ⭐ **Everything on**: phone, camera 1, Telegram alerts + video, voice | `python web_app.py --phone --camera 1 --alert "teddy bear,cow" --voice "teddy bear"` |
| Faster on Apple Silicon (Mac GPU) | add `--device mps` to any command above |
| Different port (if 8000 is taken) | add `--port 8001` |

The commands above assume `.venv` is activated. On macOS, `.venv/bin/python web_app.py`
also works without activation.

On Windows, activate the environment and replace `.venv/bin/python` with `python`, or run
`.\.venv\Scripts\python.exe web_app.py`. Use `--device cuda` instead of `--device mps` when
PyTorch has been installed for a supported NVIDIA GPU.

### 3. Wait until it's ready (about 30–40 seconds)

It loads the model, checks every camera and connects to Telegram. It's ready when you see:

```
Loading model yolo11n.pt ...
Model knows 80 objects
Cameras found: ...
Telegram bot commands are on (send /help to your bot)

  Open:  http://localhost:8000
  Phone (same Wi-Fi):  http://192.168.x.x:8000
  Press Ctrl+C to stop.
```

(`Phone (same Wi-Fi)` only appears with `--phone`; the Telegram line only appears if
Telegram is set up in `.env`.)

### 4. Open it

- **On this computer:** **http://localhost:8000**
- **On your phone:** the `Phone (same Wi-Fi)` address printed in the terminal
- Log in with the username / password from `.env` (see [Login](#-login))
- **Telegram:** send `/help` to your bot

Alerts, voice and their objects can also be switched on later in the web page (**Alerts** panel),
so you can start with the simple command and set things up in the browser.

### 5. Stop it

Click in the terminal and press **`Ctrl+C`**. Closing the terminal or VS Code also stops it.

### Is it already running? / stop a copy you can't find

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN     # shows the process using port 8000 (nothing = not running)
pkill -f web_app.py                  # stops every running copy of the server
```

Run only **one** copy at a time: two copies fight over the camera and the Telegram bot,
and the second one fails with `Address already in use`.

On Windows, find and stop a process using port 8000 with:

```powershell
netstat -ano | findstr :8000
taskkill /PID <PID_FROM_THE_PREVIOUS_COMMAND> /F
```

### Keep it running while you're away

The Mac must stay on and awake for the page, alerts and bot to work. In a **second** terminal:

```bash
caffeinate -d
```

(Press `Ctrl+C` there to let the Mac sleep again.)

On Windows, keep the computer awake using **Settings → System → Power & battery → Screen and
sleep** while the server is needed.

### Desktop-window version (no web page)

`main.py` shows the camera in a desktop window instead of a web page. It supports
`--alert` and `--voice`, but **not** the web page, login or Telegram bot commands.

```bash
.venv/bin/python main.py
```

| Key | Action |
|---|---|
| `q` or `Esc` | Quit |
| `s` | Save a snapshot (`snapshot_YYYYMMDD_HHMMSS.jpg`) |

> **First run on macOS:** you will be asked to allow **camera access** and **incoming network
> connections** for your terminal / VS Code / Python. Click **Allow**. If you missed the camera
> one, go to **System Settings → Privacy & Security → Camera**, enable your terminal/VS Code,
> and restart it.
>
> **First run on Windows:** go to **Settings → Privacy & security → Camera** and enable
> camera access plus **Let desktop apps access your camera**. When using `--phone`, allow
> Python through Windows Defender Firewall on **Private networks**.

---

## 💻 Running from VS Code

### First time

1. **File → Open Folder…** and choose the `camDetection` folder.
2. Install the **Python** extension (by Microsoft) if asked.
3. Make sure the bottom-right corner shows `.venv`. If not, open **Python: Select
   Interpreter** (`Cmd+Shift+P` on macOS or `Ctrl+Shift+P` on Windows) and choose the
   interpreter inside `.venv`.

### Start it from the VS Code terminal (step by step)

**1. Open the terminal:** press `` Ctrl+` `` (the key below `Esc`), or use the menu
**Terminal → New Terminal**.

**2. Start the app:**

```bash
python web_app.py --phone --camera 1 --alert "teddy bear,cow" --voice "teddy bear"
```

**3. Wait about 30–40 seconds** until you see:

```
Telegram bot commands are on (send /help to your bot)

  Open:  http://localhost:8000
  Phone (same Wi-Fi):  http://10.143.x.x:8000
```

**4. Use it:**

- **Telegram:** send `/help` to your bot. Send a *new* command: commands sent while the
  program was off are skipped on purpose.
- **Browser:** open **http://localhost:8000** and log in (**zahra** / **12345**).

**5. Stop it:** click in the terminal and press **`Ctrl+C`**.

> - **Keep the terminal open.** Closing the terminal or VS Code stops the server *and* the
>   Telegram bot. The bot only replies while the server is running.
> - **`Address already in use`** means it is already running somewhere. Stop the other one
>   first (`Ctrl+C` in that terminal).
> - The first time, macOS may ask to allow **camera access** and **incoming network
>   connections** for VS Code / Python. Click **Allow** for both.
> - To control it from your phone while you're away, keep the Mac awake: run `caffeinate -d`
>   in a second terminal.

### Or start it with one click (F5)

Press **`Cmd+Shift+D`**, pick a configuration from the dropdown, and press **F5** (or ▶).
Stop it with the red ⏹ button at the top.

| Configuration | What it runs |
|---|---|
| Web (browser) | `web_app.py`, open http://localhost:8000 |
| Web (browser + phone on same Wi-Fi) | `web_app.py --phone` |
| Web + Telegram + Voice (teddy bear, cow) | Web + phone + camera 1 + alerts + voice |
| Camera Detection | `main.py` (desktop window) |
| Camera Detection (Apple GPU) | `main.py --device mps` |

You can also type any command from this README in the VS Code terminal (`` Ctrl+` ``).
To change the options of a configuration, edit `"args"` in `.vscode/launch.json`.

---

## 🔐 Login

The web page asks for a username and password. They are stored in `.env` (not in the code):

```
WEB_USERNAME="zahra"
WEB_PASSWORD="12345"
```

- To change them, edit `.env` and restart the program.
- `.env` also gets a `FLASK_SECRET_KEY` line, created automatically on the first start. Leave it
  there: it keeps you logged in after a restart.
- You stay logged in for 7 days. Use **Log out** (top right) to log out.
- To run without a login (e.g. only on your own Mac), add `--no-login`.

> ⚠️ `12345` is very easy to guess. If you use `--phone` on shared Wi-Fi (campus, café),
> change it to a longer password.

---

## 🌐 The web dashboard

| Section | What it does |
|---|---|
| **Live video** | Camera feed with boxes and labels. **⛶ Fullscreen** = full screen |
| **📸 Snapshot** | Download a snapshot of the current frame |
| **🔄 Switch camera** | Jump to the next camera (skips cameras with a black picture) |
| **Right now** | Number of objects on screen and FPS |
| **Objects seen** | Count of each object type right now |
| **Alerts → 📲 Telegram alerts** | Switch Telegram alerts on/off |
| **Alerts → 🎥 5-second video** | Switch the 5-second video on/off (off = photo only) |
| **Alerts → Objects for Telegram alerts** | Choose which objects send a Telegram alert. Tap **×** to remove, **+ Add object…** to add |
| **Alerts → 🔊 Voice alert** | Switch the voice alert on/off |
| **Alerts → Objects for voice alerts** | Choose which objects the voice speaks for |
| **▶️ Test voice** | Hear a test sentence from the computer |
| **📸 Send photo to Telegram** | Send the current camera picture to your Telegram now |
| **Settings → Camera** | Preview picture of every camera found. Tap one to switch. *Dark* = black picture. **🔍 Rescan** = look for cameras again (e.g. after plugging one in or connecting your iPhone) |
| **Settings → Minimum confidence** | Lower = detects more (but more mistakes); higher = stricter |
| **Settings → Text size** | Label text size |
| **Recent activity** | Timeline of what was seen |

---

## 📲 Telegram alerts

Get a message with a photo and video on your phone when a specific object appears, from
anywhere, even when your phone is not on the same Wi-Fi.

### 1. Create a bot (once)

1. In Telegram, open **@BotFather** and send `/newbot`. Choose a name and username.
2. BotFather gives you a **token** like `7123456789:AAH...`.
3. Add this line to the `.env` file in the project folder (create the file if it doesn't exist):
   ```
   TELEGRAM_BOT_TOKEN="paste-your-token-here"
   ```
4. Open your new bot in Telegram and press **Start** (or send it "hi").
5. Run:
   ```bash
   python setup_telegram.py
   ```
   This finds your chat ID, saves it to `.env`, and sends you a test message ✅.

### 2. Run with alerts

List the objects to watch after `--alert`, separated by commas. **Use quotes** when a name
has spaces.

```bash
python web_app.py --phone --alert "teddy bear,cow"
python web_app.py --phone --alert person
python main.py --alert car,motorcycle
```

> 💡 You can also start without `--alert` and pick the objects later in the web page
> (**Alerts → Objects for Telegram alerts**). Changes made in the web page or through the bot
> (alerts, voice, objects, camera) last until the program stops; the next start uses the
> command options again.

What happens when an alert object is seen:

- 🚨 It gets a **bigger, flashing red box** with a red label in capitals, e.g. **COW 91%**
- 📸 You immediately receive a **photo**: *⚠️ Alert! 1 x cow detected · 🕒 21:45:10 · Camera 0*
- 🎥 A few seconds later, a **5-second video** follows (2 s before + 3 s after the moment it
  was seen). Change the length with `--clip-seconds 10`, or `--clip-seconds 0` for photo only
- ⏱️ **Cooldown:** at most one alert per object type every 60 seconds. Change it with
  `--alert-cooldown 10` (10 s) or `--alert-cooldown 300` (5 min).

> The computer must be on with the program running (and connected to the internet) to send alerts.

### 3. Control it from Telegram (bot commands)

While `web_app.py` is running, send these to your bot (they also appear in the bot's **Menu** button):

| Command | What it does |
|---|---|
| `/help` | List all commands |
| `/photo` | Send a photo from the camera right now |
| `/status` | What the camera sees now, camera number, FPS, alerts and voice on/off |
| `/on` | Turn Telegram alerts **on** |
| `/off` | Turn Telegram alerts **off** |
| `/camera` | List the cameras found |
| `/camera 1` | Switch to camera 1 |
| `/voice on` / `/voice off` | Turn the voice alert on / off |

- Only **your** Telegram account (the chat ID in `.env`) can use the commands. Anyone else gets
  *"Sorry, you are not allowed to use this bot."*
- Commands sent while the program was off are ignored when it starts.
- Bot commands work with `web_app.py` (not `main.py`). Turn them off with `--no-bot`.

---

## 🔊 Voice alert

The computer speaks out loud using macOS `say` or Windows' built-in speech engine when chosen
objects appear:

```bash
python web_app.py --phone --voice "teddy bear"
```

> *"Alert! Teddy bear detected."*

- It speaks at most once every 10 seconds per object; change with `--voice-cooldown 30`.
- Voice objects also get the flashing red box.
- You can also switch the voice on/off and choose its objects in the web page (**Alerts** panel),
  even if you started without `--voice`.
- It can be different from the Telegram list, e.g. voice for teddy bear only, Telegram for
  teddy bear + cow:
  ```bash
  python web_app.py --phone --alert "teddy bear,cow" --voice "teddy bear"
  ```
- On Windows, speech uses an installed system voice. Malay is selected when a `ms-MY` voice is
  installed; otherwise Windows uses its default voice. Turn up the computer's volume 🔈.

---

## 🧠 Choosing a model (80 or 600 objects)

| Model | Objects | Speed (Mac GPU) | Notes |
|---|---|---|---|
| `yolo11n.pt` *(default)* | 80 | fastest | Very good at the common 80 objects (people, cars, cows, teddy bears…) |
| `yolov8n-oiv7.pt` | 600 | ~19 ms/frame | Small 600-object model; less accurate |
| `yolov8s-oiv7.pt` | 600 | ~32 ms/frame | Good balance |
| `yolov8m-oiv7.pt` | 600 | ~62 ms/frame | Most accurate of the three; use with `--device mps` |

Use a 600-object model with `--model` (it is downloaded automatically the first time):

```bash
.venv/bin/python web_app.py --phone --model yolov8m-oiv7.pt --device mps --alert "goat,chicken"
```

The 600-object models add things like **goat**, **chicken**, **duck**, **cattle**, **bull**,
**helmet**, **man**, **woman**, **boy**, **girl** and many more. The **+ Add object…** list in
the web page always shows exactly what the loaded model knows.

Test results on sample photos:

| Photo | `yolo11n` (80) | `yolov8m-oiv7` (600) |
|---|---|---|
| Goat | cow ❌ | **goat** 43% ✅ |
| Chicken | bird ⚠️ | **chicken** 96% ✅ |
| Cow | **cow** 93% ✅ | **cattle** 84% ✅ |
| Teddy bear | **teddy bear** 94% ✅ | **teddy bear** 81% ✅ |
| Water buffalo | elephant ❌ | rhinoceros ❌ |

❌ **Water buffalo** is not in either model. Detecting it reliably needs a custom-trained model
(about 100–300 labelled photos).

> Note: object names differ between models. For example, a cow is `cow` in the 80-object model
> but `cattle` in the 600-object model, so use the right name with `--alert`.

---

## ⚙️ All options

Options work with both `web_app.py` and `main.py` unless noted.

| Option | Default | Description |
|---|---|---|
| `--camera N` | `0` | Which camera to use (0, 1, 2…) |
| `--source URL` | – | *(main.py only)* Video file or IP camera, e.g. `rtsp://user:pass@192.168.1.10/stream` |
| `--model NAME` | `yolo11n.pt` | Detection model, see [Choosing a model](#-choosing-a-model-80-or-600-objects) |
| `--device mps\|cpu\|cuda` | auto | `mps` uses the Apple Silicon GPU (faster on Mac) |
| `--conf 0-1` | `0.5` | Minimum confidence. Try `0.35` if objects are missed |
| `--text-size X` | `1.0` | Label size, e.g. `1.5` = 50% bigger |
| `--width` / `--height` | `1280` / `720` | Requested camera resolution |
| `--alert LIST` | – | Telegram alert objects, e.g. `"teddy bear,cow"` |
| `--alert-cooldown S` | `60` | Seconds between alerts for the same object |
| `--clip-seconds S` | `5` | Video length sent with each alert (`0` = photo only) |
| `--voice LIST` | – | Speak out loud for these objects, e.g. `"teddy bear"` |
| `--voice-cooldown S` | `10` | Seconds before speaking again for the same object |
| `--lang en\|ms` | `en` | Label language. `ms` = Malay (optional) |
| `--no-bot` | off | *(web_app.py only)* Don't listen for Telegram commands |
| `--no-login` | off | *(web_app.py only)* Open the page without a password |
| `--phone` | off | *(web_app.py only)* Allow other devices on the same Wi-Fi to open the page |
| `--port N` | `8000` | *(web_app.py only)* Web server port |

See all options any time with `python web_app.py --help` or `python main.py --help`.

For an NVIDIA GPU on Windows, install the matching CUDA-enabled PyTorch build from the official
PyTorch installer, then use `--device cuda`. Otherwise omit `--device` to use automatic selection,
or use `--device cpu`. `mps` is only for Apple Silicon Macs.

---

## 🐄 Objects the default model can detect (80)

| Category | Objects |
|---|---|
| People | person |
| Vehicles | bicycle, car, motorcycle, airplane, bus, train, truck, boat |
| Outdoor | traffic light, fire hydrant, stop sign, parking meter, bench |
| Animals | bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe |
| Accessories | backpack, umbrella, handbag, tie, suitcase |
| Sports | frisbee, skis, snowboard, sports ball, kite, baseball bat, baseball glove, skateboard, surfboard, tennis racket |
| Kitchen | bottle, wine glass, cup, fork, knife, spoon, bowl |
| Food | banana, apple, sandwich, orange, broccoli, carrot, hot dog, pizza, donut, cake |
| Furniture | chair, couch, potted plant, bed, dining table, toilet |
| Electronics | tv, laptop, mouse, remote, keyboard, cell phone |
| Appliances | microwave, oven, toaster, sink, refrigerator |
| Household | book, clock, vase, scissors, teddy bear, hair drier, toothbrush |

For more objects (goat, chicken, helmet…), use a 600-object model (see above).

---

## 🩺 Troubleshooting

| Problem | Solution |
|---|---|
| **Python command not found** | macOS: use `.venv/bin/python` or activate with `source .venv/bin/activate`. Windows: install Python with the launcher enabled, then use `py`, or run `.\.venv\Scripts\python.exe` |
| **Page doesn't open right after starting** | Startup takes about 30–40 seconds. Wait for `Open: http://localhost:8000` in the terminal, then refresh |
| **Black picture** | That camera isn't giving an image (e.g. iPhone locked, or covered). Tap another camera under **Settings → Camera**, press **🔄 Switch camera**, or send `/camera 1` to the bot |
| **Picture looks zoomed in / wrong camera** | Your iPhone may be connected as a Continuity Camera. Try `--camera 1`, or turn off **Center Stage** in Control Center → Video Effects. Run `python check_camera.py` to save a test picture from every camera into `camera_check/` |
| **"Could not open camera"** | macOS: allow terminal/VS Code under **System Settings → Privacy & Security → Camera**. Windows: enable camera access and **Let desktop apps access your camera**, then close other apps using the camera |
| **Object not detected** | Better lighting, show the whole object, and lower the confidence (`--conf 0.35` or the web slider). For objects outside the 80, use a 600-object model |
| **"Unknown object for --alert"** | The loaded model doesn't know that name. Check the **+ Add object…** list in the web page, or try a 600-object model |
| **Slow / low FPS** | Apple Silicon: add `--device mps`. Windows with a configured NVIDIA/PyTorch CUDA installation: add `--device cuda`. Otherwise use a smaller model (`yolo11n.pt` or `yolov8n-oiv7.pt`) |
| **Phone can't open the page** | Run with `--phone`, use the same Wi-Fi, and allow Python through the macOS or Windows firewall. Some campus/public Wi-Fi blocks this; use your phone's hotspot instead |
| **"Address already in use"** | It is already running somewhere. Stop it with `Ctrl+C`, use `--port 8001`, or use `pkill -f web_app.py` on macOS / `netstat -ano \| findstr :8000` then `taskkill /PID … /F` on Windows |
| **Bot doesn't reply to commands** | Most often the server is **not running**: the bot only replies while `web_app.py` runs. Start it (see [Start it from the VS Code terminal](#start-it-from-the-vs-code-terminal-step-by-step)), wait for `Telegram bot commands are on`, then send the command **again** (commands sent while it was off are skipped). Also make sure only **one** copy is running, and that it's `web_app.py`, not `main.py` |
| **No voice** | Turn up the volume, enable **🔊 Voice alert**, add an object, and press **▶️ Test voice**. macOS requires `say`; Windows requires Windows PowerShell and an installed system speech voice |
| **Forgot the password** | Open `.env` and look at `WEB_USERNAME` / `WEB_PASSWORD` |
| **No Telegram alert** | Run `python setup_telegram.py` again to test. Check the object name in `--alert` and the **Telegram alerts** switch on the web page. Remember the 60 s cooldown |

---

## 📁 Project structure

```
camDetection/
├── web_app.py                  # Browser version (Flask server)
├── main.py                     # Desktop window version
├── setup_telegram.py           # One-time Telegram setup + test message
├── check_camera.py             # Saves a test picture from every camera
├── cam_detection/
│   ├── detector.py             # YOLO detection + drawing boxes/labels
│   ├── camera.py               # Cross-platform OpenCV camera backends
│   ├── translations.py         # Optional Malay object names (--lang ms)
│   ├── telegram_alert.py       # Telegram photo + video alerts, cooldown
│   ├── telegram_bot.py         # Telegram commands (/photo, /status, /help…)
│   └── voice.py                # Voice alert (macOS + Windows)
├── web/index.html              # The web dashboard page
├── web/login.html              # The login page
├── .vscode/                    # VS Code run configurations
├── requirements.txt            # Python libraries
├── .env                        # Telegram token, chat ID, web login (private!)
├── yolo11n.pt                  # Default detection model (80 objects)
└── yolov8*-oiv7.pt             # Optional 600-object models (downloaded when used)
```

---

## 🔒 Privacy & security

- **Never share `.env`.** It contains your Telegram bot token and web password. It is listed in
  `.gitignore`, so it is not uploaded to Git/GitHub. If the token leaks, send `/revoke` to
  @BotFather and put the new token in `.env`.
- With **`--phone`**, anyone on the same Wi-Fi network can reach the page, so the **login** is
  what protects your camera. Use a strong password on shared Wi-Fi.
- Only your own Telegram chat can control the bot.
- All detection runs **on your own computer**. Images only leave your computer when they go to
  your Telegram: an alert (photo + video), `/photo`, or the **📸 Send photo to Telegram** button.
