import os
import base64
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from groq import Groq

app = Flask(__name__)

# --- ดึงค่าเชื่อมต่อ ---
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 1. ส่วนแชทปกติ + ปุ่ม Rich Menu ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text
    
    if user_text == "[โหมดระดมสมอง]":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🧠 เข้าสู่โหมดระดมสมอง! ส่งสิ่งที่อยากให้ช่วยคิดมาได้เลย"))
        return 
    elif user_text == "[โหมดแชทหลัก]":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="💬 กลับสู่โหมดแชทหลักแล้วครับ"))
        return 

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": user_text}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=completion.choices[0].message.content))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ สมองขัดข้องนิดหน่อย"))

# --- 2. ส่วนวิเคราะห์รูปภาพ (แก้ไขให้เสถียรขึ้น) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    # ดึงรูปจาก LINE
    message_content = line_bot_api.get_message_content(event.message.id)
    image_data = message_content.content
    base64_image = base64.b64encode(image_data).decode('utf-8')

    try:
        # ใช้โมเดลตัว 90b ที่แรงกว่าเดิม
        response = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "รูปนี้คืออะไรครับ?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        # ถ้าพัง ให้บอกเหตุผลด้วย จะได้รู้ว่าพังตรงไหน
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"มองไม่เห็นครับ (Error: {str(e)[:50]})"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
