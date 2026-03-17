import os
import base64
import fitz  # สำหรับอ่าน PDF (PyMuPDF)
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    ImageMessage, FileMessage
)
from groq import Groq

# --- [INITIALIZE] เริ่มต้นระบบ ---
app = Flask(__name__)

# ดึงค่า Config จาก Environment Variables (ใน Render)
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

# --- [WEBHOOK] ส่วนรับข้อมูลจาก LINE ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- [SECTION 1: TEXT] จัดการข้อความและปุ่ม Rich Menu ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text
    
    # ดักจับคำสั่งจาก Rich Menu (ระบบระดมสมองของคุณ)
    if user_text == "[โหมดระดมสมอง]":
        reply = "🧠 **เข้าสู่โหมดระดมสมอง!**\nส่งหัวข้อที่อยากให้ช่วยคิดมาได้เลยครับ สถาปนิก AI พร้อมลุย!"
    elif user_text == "[โหมดแชทหลัก]":
        reply = "💬 **กลับสู่โหมดแชทหลัก**\nคุยกับผมได้ตามปกติเลยครับ มีอะไรให้ช่วยไหม?"
    else:
        # ส่งไปถาม Groq รุ่นตัวแรง (70B)
        try:
            chat_completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "คุณคือ Synapse AI ผู้ช่วยอัจฉริยะ ตอบคำถามอย่างชาญฉลาด เป็นกันเอง และให้ข้อมูลเชิงลึก"},
                    {"role": "user", "content": user_text}
                ]
            )
            reply = chat_completion.choices[0].message.content
        except:
            reply = "ขออภัยครับ สมองขัดข้องนิดหน่อย ลองใหม่อีกทีนะครับ"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

# --- [SECTION 2: IMAGE] จัดการรูปภาพ (Vision) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    # ดึงรูปจาก LINE และแปลงเป็น Base64
    content = line_bot_api.get_message_content(event.message.id)
    b64_img = base64.b64encode(content.content).decode('utf-8')

    try:
        # ใช้โมเดล Vision วิเคราะห์รูป
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "ช่วยวิเคราะห์รูปนี้แบบละเอียดหน่อยครับ?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                ]
            }]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"มองไม่ชัดเลยครับ (Error: {str(e)[:30]})"))

# --- [SECTION 3: FILE] จัดการไฟล์ PDF ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    if not event.message.file_name.lower().endswith('.pdf'):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ตอนนี้ผมรับได้เฉพาะไฟล์ PDF นะครับ"))
        return

    # บันทึกไฟล์ชั่วคราวเพื่ออ่าน
    content = line_bot_api.get_message_content(event.message.id)
    with open("temp.pdf", "wb") as f:
        f.write(content.content)

    try:
        # อ่านข้อความจาก PDF
        doc_text = ""
        with fitz.open("temp.pdf") as doc:
            for page in doc:
                doc_text += page.get_text()

        # ส่งข้อความไปให้ AI สรุป
        summary = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "คุณคือผู้เชี่ยวชาญด้านสรุปเอกสาร สรุปใจความสำคัญเป็นข้อๆ ให้เข้าใจง่ายที่สุด"},
                {"role": "user", "content": doc_text[:4000]} # ป้องกันข้อความยาวเกินจำกัด
            ]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📄 **สรุปไฟล์ {event.message.file_name}:**\n\n{summary.choices[0].message.content}"))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขอโทษครับ ผมอ่านไฟล์นี้ไม่ได้"))
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")

# --- [RUN] รันแอปพลิเคชัน ---
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
