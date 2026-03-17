import os
import base64
import fitz
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage, FileMessage
from groq import Groq
from supabase import create_client, Client

app = Flask(__name__)

# --- การตั้งค่าการเชื่อมต่อ (Config) ---
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

# เชื่อมต่อ Supabase
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- ระบบแชท + จดจำ (Memory) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    
    # 1. บันทึกสิ่งที่ผู้ใช้พิมพ์ลง Database
    supabase.table("messages").insert({"user_id": user_id, "text": user_text}).execute()

    # 2. ดึงประวัติการคุย 3 ข้อความล่าสุดมาให้ AI "ระลึกชาติ"
    history = supabase.table("messages").select("text").eq("user_id", user_id).order("created_at", desc=True).limit(3).execute()
    past_chats = [item['text'] for item in history.data[::-1]]
    context = "\n".join(past_chats)

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"คุณคือ Synapse AI ที่จำเรื่องราวได้ นี่คือสิ่งที่คุยกันก่อนหน้า:\n{context}"},
                {"role": "user", "content": user_text}
            ]
        )
        reply = completion.choices[0].message.content
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยครับ สมองขัดข้องนิดหน่อย"))

# --- ระบบดูรูปภาพ (Vision) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    content = line_bot_api.get_message_content(event.message.id)
    b64_img = base64.b64encode(content.content).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": "ช่วยวิเคราะห์รูปนี้หน่อย?"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="มองไม่เห็นครับ"))

# --- ระบบอ่าน PDF ---
@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    if not event.message.file_name.lower().endswith('.pdf'): return
    content = line_bot_api.get_message_content(event.message.id)
    with open("temp.pdf", "wb") as f: f.write(content.content)
    try:
        text = ""
        with fitz.open("temp.pdf") as doc:
            for page in doc: text += page.get_text()
        summary = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": "สรุป PDF นี้ที"}, {"role": "user", "content": text[:4000]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=summary.choices[0].message.content))
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="อ่านไฟล์ไม่ได้ครับ"))
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
