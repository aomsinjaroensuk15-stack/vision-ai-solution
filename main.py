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
        # แก้ปัญหาที่ 1: ตั้งค่าเริ่มต้นแบบเงียบๆ ไม่ทักทายซ้ำซาก
        user_sessions[user_id] = [{"role": "system", "content": "คุณคือ Vision AI Solution ติวเตอร์อัจฉริยะ ตอบคำถามอย่างชาญฉลาดและกระชับ"}]
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
    
    history.append({"role": "user", "content": user_text})
    if len(history) > 11: history = [history[0]] + history[-10:] # เก็บความจำ 10 ประโยคล่าสุด
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history
        )
        ai_response = completion.choices[0].message.content
        history.append({"role": "assistant", "content": ai_response})
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_response))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ สมองเบลอนิดหน่อย ลองใหม่นะ!"))

# --- 2. ระบบจัดการรูปภาพ (Vision - แก้ปัญหาตามองไม่เห็น) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        # รับรูปจาก LINE
        message_content = line_bot_api.get_message_content(event.message.id)
        base64_image = base64.b64encode(message_content.content).decode('utf-8')
        
        # ส่งให้โมเดล Vision ตัวใหญ่ที่สุด (90B)
        response = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "ช่วยวิเคราะห์รูปนี้อย่างละเอียด หรือสรุปข้อความในรูปให้ทีครับ?"},
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
        # ถ้ายังพลาด จะแจ้ง Error สั้นๆ เพื่อให้เรารู้สาเหตุ
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ดวงตามีปัญหาเล็กน้อยครับ: {str(e)[:50]}"))

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
            
            # สรุปเนื้อหาแบบ Step-by-Step
            prompt = f"สรุปเนื้อหาจากไฟล์ {file_name} นี้เป็น 3 หัวใจสำคัญ และตั้งคำถามทดสอบ 3 ข้อ:\n\n{text[:4000]}"
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}]
            )
            summary = completion.choices[0].message.content

            # ส่งเป็น Flex Message สีดำหรูหรา
            flex_content = {
                "type": "bubble",
                "header": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "💎 VISION SUMMARY", "weight": "bold", "color": "#FFFFFF"}], "backgroundColor": "#000000"},
                "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": file_name, "weight": "bold", "size": "lg"}, {"type": "text", "text": summary, "wrap": True, "size": "sm", "margin": "md"}]},
                "footer": {"type": "box", "layout": "vertical", "contents": [{"type": "button", "action": {"type": "message", "label": "📝 เริ่มทำแบบทดสอบ", "text": "ขอแบบทดสอบจากไฟล์นี้ที!"}, "style": "primary", "color": "#000000"}]}
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="PDF Summary", contents=flex_content))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="อ่าน PDF ไม่สำเร็จครับ"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
