import os
import base64
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage, FileMessage
from groq import Groq

app = Flask(__name__)

# --- เชื่อมต่อ API ---
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

# --- 1. ระบบจัดการ "ข้อความ" (แชทปกติ) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text
    if user_text in ["[โหมดระดมสมอง]", "[โหมดแชทหลัก]"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🤖 เปลี่ยนเป็น {user_text} เรียบร้อย! มีอะไรให้ช่วยไหมครับ?"))
        return

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": user_text}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=completion.choices[0].message.content))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ สมองเบลอนิดหน่อย ลองใหม่นะ!"))

# --- 2. ระบบจัดการ "รูปภาพ" (ดวงตา AI) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    base64_image = base64.b64encode(message_content.content).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": "อธิบายรูปนี้ทีครับ?"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"มองไม่เห็นครับ (Error: {str(e)[:30]})"))

# --- 3. ระบบจัดการ "ไฟล์ PDF" (เครื่องอ่านเอกสาร) ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    file_name = event.message.file_name
    if file_name.endswith('.pdf'):
        # ส่งข้อความตอบรับก่อน
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📄 รับไฟล์ {file_name} แล้ว! กำลังตรวจสอบเนื้อหาเบื้องต้น..."))
        # หมายเหตุ: การแกะไส้ใน PDF ต้องใช้ Library เพิ่มเติม (เช่น PyMuPDF) 
        # ในขั้นตอนนี้ บอทจะรับรู้ว่ามีไฟล์เข้าและพร้อมประมวลผลขั้นต่อไปครับ
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ส่งมาเป็นไฟล์ .pdf นะครับน้องบอทถึงจะอ่านออก!"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
