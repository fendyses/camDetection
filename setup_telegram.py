"""Find your Telegram chat ID and save it to .env, then send a test message.

1. Put TELEGRAM_BOT_TOKEN="..." in .env
2. Open your bot in Telegram and press Start (or send it any message)
3. Run:  python setup_telegram.py
"""
import requests

from cam_detection.telegram_alert import load_env, save_env_value

token = load_env().get("TELEGRAM_BOT_TOKEN")
if not token:
    raise SystemExit("TELEGRAM_BOT_TOKEN not found in .env")

api = f"https://api.telegram.org/bot{token}"
me = requests.get(f"{api}/getMe", timeout=15).json()
if not me.get("ok"):
    raise SystemExit(f"The token was rejected by Telegram: {me.get('description')}")
print(f"Bot: @{me['result']['username']}")

updates = requests.get(f"{api}/getUpdates", timeout=15).json().get("result", [])
chats = {}
for u in updates:
    msg = u.get("message") or u.get("edited_message") or {}
    chat = msg.get("chat")
    if chat:
        chats[chat["id"]] = chat.get("first_name") or chat.get("title") or chat.get("username", "")
if not chats:
    raise SystemExit(f"No messages found. Open t.me/{me['result']['username']} in Telegram, "
                     "press Start (or send 'hi'), then run this again.")

chat_id, name = list(chats.items())[-1]
save_env_value("TELEGRAM_CHAT_ID", str(chat_id))
print(f"Found chat with {name} (id {chat_id}) and saved it to .env")

r = requests.post(f"{api}/sendMessage", timeout=15, data={
    "chat_id": chat_id, "text": "✅ camDetection connected! Alerts will be sent here."}).json()
print("Test message sent ✅" if r.get("ok") else f"Test message failed: {r.get('description')}")
