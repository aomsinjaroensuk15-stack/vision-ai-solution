import os
import base64
import fitz  # สำหรับ PyMuPDF
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    ImageMessage, FileMessage
)
from groq import Groq
from supabase import create_client, Client
from axiom import Client as AxiomClient

# --- [1. INITIALIZE] เริ่มต้นระบบทั้งหมด ---
app = Flask(__name__)

# ดึงค่าจาก Environment Variables ใน Render
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
groq_client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

# เชื่อมต่อ Supabase (ฐานข้อมูลความจำ)
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"), 
    os.environ.get("SUPABASE_KEY")
)

# เชื่อมต่อ Axiom (ศูนย์ควบคุม Log)
axiom_client = AxiomClient(os.environ.get("AXIOM_TOKEN"))
AXIOM_DATASET = os.environ.get("AXIOM_DATASET")

# ฟังก์ชันส่งข้อมูลไป Axiom
def log_to_axiom(event_type, data):
    try:
        axiom_client.ingest_events(AXIOM_DATASET, [{"type": event_type, "data": data}])
    except:
        pass # ป้องกันบอทพังถ้า Axiom มีปัญหา

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- [2. TEXT SYSTEM] แชทปกติ + ระดมสมอง + ศูนย์ควบคุม ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    
    # ส่ง Log ไป Axiom ทันที
    log_to_axiom("text_received", {"user": user_id, "text": user_text})

    # ปุ่มระบบศูนย์ควบคุม AI (โชว์ Analytics)
    if user_text == "ศูนย์ควบคุม AI":
        try:
            res = supabase.table("messages").select("id", count="exact").execute()
            msg_count = res.count if res.count else 0
            reply = (f"🖥️ [ ศูนย์ควบคุม Vision AI ]\n"
                     f"✅ สถานะ: Online (Render)\n"
                     f"📊 บันทึกใน Database: {msg_count} ข้อความ\n"
                     f"📡 Axiom Logs: Connected")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
        except Exception as e:
            log_to_axiom("error", {"msg": str(e)})

    # โหมดระดมสมอง (Rich Menu)
    if user_text == "[โหมดระดมสมอง]":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🧠 เข้าสู่โหมดระดมสมอง! ส่งหัวข้อมาได้เลยครับ"))
        return

    # บันทึกลง Supabase และดึงความจำ 3 ข้อความล่าสุด
    try:
        supabase.table("messages").insert({"user_id": user_id, "text": user_text}).execute()
        history = supabase.table("messages").select("text").eq("user_id", user_id).order("created_at", desc=True).limit(3).execute()
        past_chats = [item['text'] for item in history.data[::-1]]
        context = "\n".join(past_chats)
        
        # ส่งให้ Groq ตอบ (รุ่น 70B)
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"คุณคือ Synapse AI ผู้ช่วยอัจฉริยะ นี่คือบริบทก่อนหน้า:\n{context}"},
                {"role": "user", "content": user_text}
            ]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=completion.choices[0].message.content))
    except Exception as e:
        log_to_axiom("error", {"msg": str(e)})

# --- [3. VISION SYSTEM] วิเคราะห์รูปภาพ ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    log_to_axiom("image_received", {"user": event.source.user_id})
    content = line_bot_api.get_message_content(event.message.id)
    b64_img = base64.b64encode(content.content).decode('utf-8')
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": "วิเคราะห์รูปนี้?"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        log_to_axiom("error_vision", {"msg": str(e)})

# --- [4. PDF SYSTEM] สรุปเอกสาร ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    if not event.message.file_name.lower().endswith('.pdf'): return
    log_to_axiom("pdf_received", {"user": event.source.user_id, "file": event.message.file_name})
    
    content = line_bot_api.get_message_content(event.message.id)
    with open("temp.pdf", "wb") as f: f.write(content.content)
    try:
        text = ""
        with fitz.open("temp.pdf") as doc:
            for page in doc: text += page.get_text()
        
        summary = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": "สรุปเนื้อหา PDF นี้เป็นข้อๆ"}, {"role": "user", "content": text[:4000]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📄 สรุป {event.message.file_name}:\n\n{summary.choices[0].message.content}"))
    except Exception as e:
        log_to_axiom("error_pdf", {"msg": str(e)})
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
