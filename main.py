import os
import base64
import fitz  # สำหรับอ่าน PDF
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage, FileMessage
from groq import Groq

app = Flask(__name__)

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

# --- 1. ระบบแชทปกติ + 2. ระบบระดมสมอง (Rich Menu) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text
    
    # ดักจับคำสั่งจาก Rich Menu
    if user_text == "[โหมดระดมสมอง]":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🧠 เข้าสู่โหมดระดมสมอง! ส่งหัวข้อที่อยากให้ช่วยคิดมาได้เลยครับ เดี๋ยวผมช่วยหาไอเดียเจ๋งๆ ให้"))
        return 
    elif user_text == "[โหมดแชทหลัก]":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="💬 กลับสู่โหมดแชทหลักแล้วครับ คุยกับผมได้ตามปกติเลย"))
        return 

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "คุณคือ Synapse AI ผู้ช่วยอัจฉริยะ ตอบคำถามอย่างชาญฉลาด เป็นกันเอง และให้ข้อมูลเชิงลึก"},
                {"role": "user", "content": user_text}
            ]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=completion.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ สมองขัดข้องนิดหน่อย ลองใหม่อีกทีนะ"))

# --- 3. ระบบดูรูปภาพ ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    image_data = message_content.content
    base64_image = base64.b64encode(image_data).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": "ช่วยสรุปหรืออธิบายรูปนี้ให้หน่อยครับ?"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"โอ๊ะ! มองรูปไม่ชัดเลยครับ (Error: {str(e)[:50]})"))

# --- 4. ระบบอ่าน PDF ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    if not event.message.file_name.lower().endswith('.pdf'):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ตอนนี้ผมรับได้เฉพาะไฟล์ PDF เท่านั้นครับ"))
        return

    message_content = line_bot_api.get_message_content(event.message.id)
    with open("temp.pdf", "wb") as f:
        f.write(message_content.content)

    try:
        text = ""
        with fitz.open("temp.pdf") as doc:
            for page in doc:
                text += page.get_text()

        summary_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "คุณคือผู้เชี่ยวชาญด้านการสรุปเอกสาร ช่วยสรุปเนื้อหาสำคัญจากข้อความต่อไปนี้เป็นข้อๆ ให้เข้าใจง่าย"},
                {"role": "user", "content": text[:4000]}
            ]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📑 สรุปไฟล์ {event.message.file_name}:\n\n{summary_response.choices[0].message.content}"))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ อ่านไฟล์นี้ไม่ได้จริงๆ"))
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
