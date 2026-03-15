import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = Flask(__name__)

# --- 1. ตั้งค่าสมอง Gemini ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
# ใช้รุ่น 2.0 Flash ตัวล่าสุดที่คุณต้องการ
model = genai.GenerativeModel(
    model_name='gemini-2.0-flash',
    system_instruction="คุณคือ Synapse AI ผู้ช่วยอัจฉริยะ ตอบคำถามอย่างชาญฉลาด กระชับ และเป็นกันเอง"
)

# --- 2. ตั้งค่าการเชื่อมต่อ LINE ---
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

@app.route("/", methods=['GET'])
def index():
    return "Synapse AI is Online!"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    try:
        # สั่งให้ Gemini คิดหาคำตอบ
        response = model.generate_content(user_text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.text))
    except Exception as e:
        # ถ้าพัง ให้บอกสาเหตุออกมาเลย จะได้แก้ถูกจุด
        error_msg = str(e)
        print(f"Error: {error_msg}")
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=f"สมองขัดข้อง: {error_msg[:50]}...")
        )

if __name__ == "__main__":
    # Render จะบังคับใช้ Port 10000 เป็นค่าเริ่มต้น
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
