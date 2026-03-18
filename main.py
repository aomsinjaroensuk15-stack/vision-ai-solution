import os
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
import google.generativeai as genai

app = Flask(__name__)

# --- 1. การตั้งค่าระบบ (Configuration) ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
VESPA_URL = os.environ.get('VESPA_URL') # URL จาก Ngrok
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 2. ฟังก์ชันสมองส่วนความจำ (Vespa Functions) ---

def save_to_vespa(user_id, text_content):
    """บันทึกความจำลง Vespa"""
    try:
        # จำลองค่า Embedding (ในอนาคตควรใช้ model.embed_content)
        dummy_embedding = [0.1] * 1024 
        url = f"{VESPA_URL}/document/v1/memory/memory/docid/{user_id}_{os.urandom(4).hex()}"
        data = {
            "fields": {
                "user_id": user_id,
                "content": text_content,
                "embedding": {"values": dummy_embedding}
            }
        }
        requests.post(url, json=data)
    except Exception as e:
        print(f"Vespa Save Error: {e}")

def get_memory(user_id, query):
    """ดึงความจำที่เกี่ยวข้องจาก Vespa"""
    try:
        url = f"{VESPA_URL}/search/"
        yql = f"select content from memory where user_id contains '{user_id}'"
        params = {
            "yql": yql,
            "hits": 3,
            "ranking": "default"
        }
        res = requests.get(url, params=params).json()
        hits = res.get('root', {}).get('children', [])
        memories = [h['fields']['content'] for h in hits if 'fields' in h]
        return "\n".join(memories)
    except:
        return ""

# --- 3. จุดรับสัญญาณ (Webhook & Handlers) ---

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_msg = event.message.text

    # STEP A: ระลึกชาติ (ดึงความจำเก่าจาก Vespa)
    past_memories = get_memory(user_id, user_msg)
    
    # STEP B: ปรุงคำตอบด้วย Gemini
    prompt = f"""คุณคือ Sovereign AI (Vision AI Solution) ผู้ช่วยที่ชาญฉลาด
    ข้อมูลความจำในอดีตของผู้ใช้: {past_memories}
    คำถามปัจจุบัน: {user_msg}
    จงตอบคำถามโดยใช้ความจำที่มี ถ้าไม่มีให้ตอบตามความเหมาะสม"""
    
    response = model.generate_content(prompt)
    bot_reply = response.text

    # STEP C: บันทึกความจำใหม่ลง Vespa
    save_to_vespa(user_id, user_msg)
    save_to_vespa(user_id, bot_reply)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=bot_reply))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
