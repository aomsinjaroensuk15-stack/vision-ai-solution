import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from groq import Groq

app = Flask(__name__)

# --- 1. ตั้งค่าสมอง Groq (Llama 3) ---
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# --- 2. ตั้งค่าการเชื่อมต่อ LINE ---
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

@app.route("/", methods=['GET'])
def index():
    return "Synapse AI (Groq Edition) is Online!"

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
        # สั่งให้ Groq คิดหาคำตอบ (ใช้ Llama 3 70B ตัวแรง)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "คุณคือ Synapse AI ผู้ช่วยอัจฉริยะ ตอบคำถามอย่างชาญฉลาด กระชับ และเป็นกันเอง"},
                {"role": "user", "content": user_text}
            ],
            model="llama-3.3-70b-versatile",
        )
        response_text = chat_completion.choices[0].message.content
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response_text))
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=f"ระบบขัดข้อง: {str(e)[:50]}...")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
