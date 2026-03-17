import os
import base64
import fitz  # PyMuPDF สำหรับอ่าน PDF
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

user_sessions = {}

def get_chat_history(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = [{"role": "system", "content": "คุณคือ Vision AI Solution ผู้ช่วยที่จำบทสนทนาได้และอ่าน PDF ได้"}]
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

# --- 1. ระบบข้อความ ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    history = get_chat_history(user_id)
    history.append({"role": "user", "content": user_text})
    if len(history) > 11: history = [history[0]] + history[-10:]
    try:
        completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=history)
        ai_response = completion.choices[0].message.content
        history.append({"role": "assistant", "content": ai_response})
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_response))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="สมองล้านิดหน่อยครับ"))

# --- 2. ระบบรูปภาพ ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    base64_image = base64.b64encode(message_content.content).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": "วิเคราะห์รูปนี้ทีครับ?"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="มองไม่เห็นครับ"))

# --- 3. ระบบอ่านไฟล์ PDF (อัปเกรดแล้ว!) ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    file_name = event.message.file_name
    if file_name.endswith('.pdf'):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📑 กำลังแกะเนื้อหาจาก {file_name}..."))
        
        # ดึงไฟล์และอ่านข้อความ
        message_content = line_bot_api.get_message_content(event.message.id)
        with open(file_name, "wb") as f:
            f.write(message_content.content)
        
        doc = fitz.open(file_name)
        text = ""
        for page in doc: text += page.get_text()
        doc.close()
        os.remove(file_name) # อ่านเสร็จแล้วลบไฟล์ทิ้งเพื่อประหยัดที่

        # ส่งข้อความที่แกะได้ไปให้ AI สรุป
        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": f"สรุปเนื้อหาจากไฟล์ PDF นี้ให้หน่อย:\n\n{text[:5000]}"}] # ส่งไป 5000 ตัวอักษรแรก
            )
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"✅ สรุปเนื้อหา:\n{completion.choices[0].message.content}"))
        except:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text="สรุปไฟล์ไม่ได้ครับ"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="รับเฉพาะ PDF นะครับ!"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
