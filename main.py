import os
import base64
import fitz  # PyMuPDF
import httpx # ใช้แทน axiom-python เพื่อความลีน
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    ImageMessage, FileMessage
)
from groq import Groq
from supabase import create_client, Client

app = Flask(__name__)

# --- [1. CONFIG] ---
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
groq_client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

# เชื่อมต่อ Supabase
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"), 
    os.environ.get("SUPABASE_KEY")
)

# ฟังก์ชันส่ง Log ไป Axiom (แบบ Lightweight ไม่ต้องใช้ Library หนัก)
def log_to_axiom(event_type, data):
    url = f"https://api.axiom.co/v1/datasets/{os.environ.get('AXIOM_DATASET')}/ingest"
    headers = {
        "Authorization": f"Bearer {os.environ.get('AXIOM_TOKEN')}",
        "Content-Type": "application/json",
    }
    payload = [{"type": event_type, "data": data}]
    try:
        with httpx.Client() as client:
            client.post(url, headers=headers, json=payload)
    except:
        pass

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- [2. TEXT & MEMORY SYSTEM] ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    
    # ส่ง Log ไป Axiom
    log_to_axiom("text_received", {"user": user_id, "text": user_text})

    # ปุ่มศูนย์ควบคุม AI
    if user_text == "ศูนย์ควบคุม AI":
        try:
            res = supabase.table("messages").select("id", count="exact").execute()
            msg_count = res.count if res.count else 0
            reply = f"🖥️ [ ศูนย์ควบคุม ]\nสถานะ: Online\nบันทึกข้อมูล: {msg_count} ข้อความ\nLogs: Active (HTTPX)"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
        except:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ เชื่อมต่อฐานข้อมูลไม่ได้"))
            return

    # จดจำลง Supabase และดึงความจำ (นี่คือส่วนที่แก้ไขให้ตอบกลับได้แม่นยำ)
    try:
        # บันทึกข้อความใหม่
        supabase.table("messages").insert({"user_id": user_id, "text": user_text}).execute()
        
        # ดึงประวัติ 3 ข้อความล่าสุด
        history = supabase.table("messages").select("text").eq("user_id", user_id).order("created_at", desc=True).limit(3).execute()
        past_chats = [item['text'] for item in history.data[::-1]]
        context = "\n".join(past_chats)
        
        # ส่งให้ AI ประมวลผล
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"คุณคือ Synapse AI ของออมสิน นี่คือสิ่งที่เคยคุยกัน:\n{context}"},
                {"role": "user", "content": user_text}
            ]
        )
        ai_reply = completion.choices[0].message.content
        
        # *** ส่งข้อความตอบกลับหาผู้ใช้ (สำคัญมาก!) ***
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_reply))
        
    except Exception as e:
        log_to_axiom("error", {"msg": str(e)})
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ สมองส่วนความจำมีปัญหา"))

# --- [3. VISION SYSTEM] ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    content = line_bot_api.get_message_content(event.message.id)
    b64_img = base64.b64encode(content.content).decode('utf-8')
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": "วิเคราะห์รูปนี้?"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="มองไม่เห็นรูปครับ"))

# --- [4. PDF SYSTEM] ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    if not event.message.file_name.lower().endswith('.pdf'): return
    content = line_bot_api.get_message_content(event.message.id)
    with open("temp.pdf", "wb") as f: f.write(content.content)
    try:
        text = ""
        with fitz.open("temp.pdf") as doc:
            for page in doc: text += page.get_text()
        summary = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": "สรุป PDF นี้"}, {"role": "user", "content": text[:4000]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=summary.choices[0].message.content))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="อ่าน PDF ไม่ได้ครับ"))
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
