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

# --- 🧠 ระบบความจำระยะสั้น (User Sessions) ---
# สร้างตัวเก็บประวัติการคุยแยกตาม User ID
user_sessions = {}

def get_chat_history(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = [
            {"role": "system", "content": "คุณคือ Vision AI Solution ผู้ช่วยอัจฉริยะที่จำบริบทการสนทนาได้ ตอบคำถามอย่างชาญฉลาดและเป็นกันเอง"}
        ]
    return user_sessions[user_id]

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 1. ระบบจัดการ "ข้อความ" (แบบมีความจำ) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    
    if user_text in ["[โหมดระดมสมอง]", "[โหมดแชทหลัก]"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🤖 เปลี่ยนเป็น {user_text} เรียบร้อย!"))
        return

    # ดึงประวัติการคุยเดิมออกมา
    history = get_chat_history(user_id)
    history.append({"role": "user", "content": user_text})

    # จำกัดความจำไว้ที่ 10 ข้อความล่าสุด (เพื่อไม่ให้ข้อมูลเยอะเกินไปจน AI งง)
    if len(history) > 11: 
        history = [history[0]] + history[-10:]

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history
        )
        ai_response = completion.choices[0].message.content
        
        # บันทึกคำตอบของ AI ลงในประวัติด้วย
        history.append({"role": "assistant", "content": ai_response})
        user_sessions[user_id] = history
        
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_response))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ สมองล้าเล็กน้อย ลองใหม่นะครับ!"))

# --- 2. ระบบจัดการ "รูปภาพ" ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    base64_image = base64.b64encode(message_content.content).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": "วิเคราะห์รูปนี้ให้หน่อยครับ?"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"มองไม่ชัดเลยครับ (Error: {str(e)[:30]})"))

# --- 3. ระบบจัดการ "ไฟล์ PDF" ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    file_name = event.message.file_name
    if file_name.endswith('.pdf'):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📄 รับไฟล์ {file_name} แล้ว! ตอนเย็นเรามาแกะเนื้อหากันครับ"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="รับเฉพาะ PDF นะครับ!"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
