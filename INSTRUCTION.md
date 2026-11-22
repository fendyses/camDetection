# Setting up camDetection on a new laptop

A checklist of everything you need to run this project on another computer.
For full details on each feature, see [README.md](README.md).

---

## 1. What you need

| Item | Notes |
|---|---|
| **Computer** | macOS, or 64-bit Windows 10/11 |
| **Python 3.10 – 3.13** | 3.12 is the safest choice. Very new versions (3.14+) may not have PyTorch support everywhere yet. On Windows, tick **"Add Python to PATH"** when installing. |
| **Git** | To download the project from GitHub (or copy the folder over by USB instead) |
| **Internet** | For the first install, the first model download, and Telegram |
| **A camera** | Built-in webcam, USB webcam, iPhone (Continuity Camera, Mac only) or an IP/CCTV stream |
| **ESP32 board** *(optional)* | Only for the road warning light/buzzer |

---

## 2. Before you leave the old laptop

Some things are **not** on GitHub. Prepare them first.

- [ ] **Push your latest code** so GitHub has the newest version:
  ```bash
  git add -A
  git commit -m "latest changes"
  git push
  ```
- [ ] **Copy the `.env` file** to a USB stick or a private place. **Never** upload it to GitHub.
  It holds your private settings:
  ```
  TELEGRAM_BOT_TOKEN="..."   # Telegram bot token
  TELEGRAM_CHAT_ID="..."     # your Telegram chat
  WEB_USERNAME="..."         # login for the web page
  WEB_PASSWORD="..."
  FLASK_SECRET_KEY="..."     # created automatically; fine to leave out
  ```
- [ ] *(Optional)* Copy the large model files (`yolov8m-oiv7.pt` etc.) if you use them, so the new laptop
  doesn't need to download them. `yolo11n.pt` downloads by itself.

**Don't copy** the `.venv` folder. It only works on the computer where it was made.

---

## 3. Install on the new laptop

### Get the project

```bash
git clone https://github.com/fendyses/camDetection.git
cd camDetection
```

Then put your **`.env`** file inside the `camDetection` folder.

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks `Activate.ps1`, run this once, then try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

The install takes a few minutes. PyTorch is a large download.

### What gets installed (`requirements.txt`)

| Package | Used for |
|---|---|
| `ultralytics` (+ PyTorch) | The YOLO object detection model |
| `opencv-python` | Reading the camera, drawing boxes |
| `flask` | The web page |
| `requests` | Sending Telegram alerts |
| `numpy`, `pillow` | Image handling and labels |
| `pyserial` | Talking to the ESP32 light over USB |

---

## 4. First run

```bash
# macOS
.venv/bin/python web_app.py

# Windows
.\.venv\Scripts\python.exe web_app.py      # or double-click run_windows.bat
```

Then open **http://localhost:8000** and log in with `WEB_USERNAME` / `WEB_PASSWORD` from `.env`.

- **Allow camera access.** On a Mac, the first run asks for camera permission for Terminal (or VS Code).
  Click **Allow**. If you clicked Don't Allow, turn it on under
  System Settings → Privacy & Security → Camera, then restart the app.
- **Windows firewall.** If you use `--phone`, Windows may ask to allow Python on the network. Allow it on
  **private** networks.
- **First start is slower.** It downloads the model (`yolo11n.pt`) and checks every camera. Give it up to a minute.

---

## 5. Camera numbers will be different

Camera numbers depend on the laptop. On the old Mac the USB webcam was `--camera 1`. On the new laptop
it may be `0` or `2`.

```bash
python check_camera.py      # saves a test picture from every camera into camera_check/
```

Look at the pictures, then start with the right number, for example:

```bash
python web_app.py --phone --camera 0 --alert cow
```

You can also switch camera from the camera picker on the web page.

---

## 6. Telegram (optional)

If you copied `.env`, Telegram already works. To check it, or to set it up fresh:

```bash
python setup_telegram.py    # finds your chat ID, saves it to .env, sends a test message
```

Only run **one copy** of the app with the same bot token at a time. Two laptops with the same token
will fight over the Telegram commands.

---

## 7. ESP32 light (optional)

- The ESP32 keeps its program, so you **don't** need to upload `esp32/cow_light/cow_light.ino` again.
  Just plug it into the new laptop with a **data** USB cable (some cables only charge).
- The app finds the board by itself (`--esp-port auto`). Check the **Road & light** card on the web page:
  it should say *Connected*.
- **Windows:** you may need the USB driver for the chip on your board: **CP210x** (Silicon Labs) or
  **CH340**. Once it's installed, the board shows up as a `COM` port in Device Manager.
- If auto-detect fails, give the port yourself: `--esp-port COM3` (Windows) or
  `--esp-port /dev/cu.usbserial-0001` (Mac).
- To change the ESP32 program: install the **Arduino IDE** and the **esp32 by Espressif** board package,
  open `cow_light.ino`, choose your board (e.g. *ESP32 Dev Module*) and upload. Serial speed is **115200**.

---

## 8. Quick check

- [ ] `pip install -r requirements.txt` finished without errors
- [ ] `.env` is in the project folder
- [ ] The web page opens and asks for a login
- [ ] You see a live picture (right camera number chosen)
- [ ] *(Optional)* `python setup_telegram.py` sends a test message
- [ ] *(Optional)* The ESP32 shows *Connected* and **Test light** makes it blink

Something not working? See the **Troubleshooting** section in [README.md](README.md).
