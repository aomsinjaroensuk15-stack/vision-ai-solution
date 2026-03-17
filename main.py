import os
import base64
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from groq import Groq

app = Flask(__name__)

# --- ตั้งค่าการเชื่อมต่อ (ดึงค่าจาก Environment Variables ใน Render) ---
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

# --- ส่วนที่ 1: ระบบจัดการ "ข้อความ" (แชทปกติ + ปุ่ม Rich Menu) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text
    
    # เช็กปุ่มจาก Rich Menu
    if user_text == "[โหมดระดมสมอง]":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🧠 เข้าสู่โหมดระดมสมอง! ส่งหัวข้อที่อยากให้ช่วยคิดมาได้เลยครับ"))
        return 
    elif user_text == "[โหมดแชทหลัก]":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="💬 กลับสู่โหมดแชทหลักแล้วครับ มีอะไรให้ช่วยไหม?"))
        return 

    # ส่งไปถาม Groq (โมเดลตัวแรง)
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "คุณคือ Synapse AI ผู้ช่วยอัจฉริยะ ตอบคำถามอย่างชาญฉลาดและเป็นกันเอง"},
                {"role": "user", "content": user_text}
            ]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=completion.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ สมองขัดข้องนิดหน่อย ลองใหม่นะ!"))

# --- ส่วนที่ 2: ระบบจัดการ "รูปภาพ" (ดวงตา AI) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    # ดึงรูปจาก LINE และแปลงเป็น Base64
    message_content = line_bot_api.get_message_content(event.message.id)
    image_data = message_content.content
    base64_image = base64.b64encode(image_data).decode('utf-8')

    try:
        # ส่งไปให้โมเดล Vision ของ Groq วิเคราะห์
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "ช่วยอธิบายรูปนี้ให้ละเอียดและดูน่าสนใจหน่อยครับ?"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="โอ๊ะ! มองรูปไม่ชัดเลยครับ ขออีกรอบได้ไหม?"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
