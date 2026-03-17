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

# ดึงค่าจาก Environment Variables
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

# ระบบจำบทสนทนา (Memory)
user_sessions = {}

def get_chat_history(user_id):
    if user_id not in user_sessions:
        # กำหนด System Prompt ให้ฉลาดและกระชับ
        user_sessions[user_id] = [{"role": "system", "content": "คุณคือ Vision AI Solution ติวเตอร์อัจฉริยะที่ช่วยสรุปบทเรียนและวิเคราะห์ภาพ ตอบคำถามอย่างเป็นกันเองและมีพลัง"}]
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

# --- 1. ระบบจัดการข้อความ (Text) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    history = get_chat_history(user_id)
    
    # เพิ่มข้อความผู้ใช้ลงในความจำ
    history.append({"role": "user", "content": user_text})
    if len(history) > 11: history = [history[0]] + history[-10:] # คุมไม่ให้ความจำล้น
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history
        )
        ai_response = completion.choices[0].message.content
        history.append({"role": "assistant", "content": ai_response})
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_response))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ ระบบประมวลผลข้อความขัดข้อง"))

# --- 2. ระบบจัดการรูปภาพ (Vision - แก้ไข Error 400) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        # ดึงรูปจาก LINE
        message_content = line_bot_api.get_message_content(event.message.id)
        base64_image = base64.b64encode(message_content.content).decode('utf-8')
        
        # ใช้ Model ตัว 11b-vision-preview ที่เสถียรกว่าสำหรับการรับภาพ
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "ช่วยวิเคราะห์หรือแปลข้อความในรูปนี้อย่างละเอียดทีครับ?"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ]
        )
        reply_text = response.choices[0].message.content
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception as e:
        # แจ้งเตือน Error แบบละเอียดเพื่อการตรวจสอบ
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ดวงตามีปัญหา: {str(e)[:100]}"))

# --- 3. ระบบจัดการ PDF (File) ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    file_name = event.message.file_name
    if file_name.lower().endswith('.pdf'):
        message_content = line_bot_api.get_message_content(event.message.id)
        temp_path = f"temp_{event.message.id}.pdf"
        
        with open(temp_path, "wb") as f:
            f.write(message_content.content)
        
        try:
            doc = fitz.open(temp_path)
            text = "".join([page.get_text() for page in doc])
            doc.close()
            os.remove(temp_path)
            
            # ส่งให้ AI สรุปเนื้อหา
            summary_prompt = f"สรุปเนื้อหาสำคัญจากไฟล์ {file_name} ออกมาเป็นข้อๆ และตั้งคำถาม 3 ข้อเพื่อทดสอบความเข้าใจ:\n\n{text[:4000]}"
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": summary_prompt}]
            )
            summary = completion.choices[0].message.content

            # ส่งเป็น Flex Message (Black Style)
            flex_content = {
                "type": "bubble",
                "header": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "💎 VISION SUMMARY", "weight": "bold", "color": "#FFFFFF", "size": "md"}], "backgroundColor": "#000000"},
                "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": file_name, "weight": "bold", "size": "lg", "color": "#000000"}, {"type": "separator", "margin": "md"}, {"type": "text", "text": summary, "wrap": True, "size": "sm", "margin": "md", "color": "#333333"}]},
                "footer": {"type": "box", "layout": "vertical", "contents": [{"type": "button", "action": {"type": "message", "label": "📝 เริ่มทำแบบทดสอบ", "text": "ขอแบบทดสอบจากไฟล์นี้ที!"}, "style": "primary", "color": "#000000"}]}
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="สรุป PDF พร้อมแล้ว!", contents=flex_content))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ไม่สามารถประมวลผล PDF ได้ครับ"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
