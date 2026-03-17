import os
import base64
import fitz  # PyMuPDF
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage, 
    FileMessage, FlexSendMessage
)
from groq import Groq

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

user_sessions = {}

def get_chat_history(user_id):
    if user_id not in user_sessions:
        # ปรับ System Prompt ให้กระชับ ไม่ต้องทักทายซ้ำซาก
        user_sessions[user_id] = [{"role": "system", "content": "คุณคือ Vision AI Solution ติวเตอร์ส่วนตัวที่เก่งที่สุด"}]
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

# --- 1. ระบบข้อความ (แก้ปัญหาทักทายซ้ำ) ---
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
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ ลองใหม่อีกครั้งนะ"))

# --- 2. ระบบรูปภาพ (แก้ปัญหาตาบอด) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    # เปลี่ยนเป็น Image Byte โดยตรงเพื่อให้เสถียรขึ้น
    base64_image = base64.b64encode(message_content.content).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview", # เปลี่ยนรุ่นที่เสถียรกว่า
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "ช่วยอธิบายสิ่งที่เห็นในรูปนี้อย่างละเอียดทีครับ?"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        print(f"Error: {e}") # ดู Error ใน Log ของ Render
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขอโทษครับ ผมมองไม่ชัด ลองส่งใหม่ได้ไหม?"))

# --- 3. ระบบ PDF (คงความเทพไว้) ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    file_name = event.message.file_name
    if file_name.endswith('.pdf'):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📊 วิเคราะห์ {file_name}..."))
        message_content = line_bot_api.get_message_content(event.message.id)
        with open(file_name, "wb") as f: f.write(message_content.content)
        doc = fitz.open(file_name)
        text = "".join([page.get_text() for page in doc])
        doc.close()
        os.remove(file_name)
        try:
            prompt = f"สรุปเนื้อหาจาก PDF นี้เป็นข้อๆ 3 ข้อ และตั้งคำถาม 3 ข้อเพื่อทดสอบฉัน:\n\n{text[:3000]}"
            completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
            summary = completion.choices[0].message.content
            
            # Flex Message (คงเดิม)
            flex_content = {
                "type": "bubble", "header": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "💎 VISION SUMMARY", "weight": "bold", "color": "#FFFFFF"}], "backgroundColor": "#000000"},
                "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": file_name, "weight": "bold", "size": "xl"}, {"type": "text", "text": summary, "wrap": True, "size": "sm", "margin": "md"}]},
                "footer": {"type": "box", "layout": "vertical", "contents": [{"type": "button", "action": {"type": "message", "label": "📝 เริ่มทำแบบทดสอบ", "text": "ตั้งคำถามจากไฟล์นี้ให้ที!"}, "style": "primary", "color": "#000000"}]}
            }
            line_bot_api.push_message(event.source.user_id, FlexSendMessage(alt_text="Summary", contents=flex_content))
        except:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text="สรุปไม่ได้ครับ"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
