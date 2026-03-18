import os, base64, httpx, hashlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from groq import Groq
from supabase import create_client
from PIL import Image
import io

app = Flask(__name__)

# --- [CONFIG] ---
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
groq_client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

def get_stable_vector(text):
    h = hashlib.sha256(text.encode()).digest()
    return [float((h[i % len(h)] / 255.0) * 2 - 1) for i in range(1024)]

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    try:
        # 1. ดึงความจำ (Memory Recall)
        current_vec = get_stable_vector(user_text)
        memories = supabase.rpc("match_memories", {
            "query_embedding": current_vec, "match_threshold": 0.3, "match_count": 5, "p_user_id": user_id
        }).execute()
        context = "\n".join([m['content'] for m in memories.data]) if memories.data else ""

        # 2. ส่งให้ AI (Chat & Idea Mode)
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"คุณคือ Sovereign AI ที่ฉลาดรอบด้าน อดีตที่จำได้:\n{context}"},
                {"role": "user", "content": user_text}
            ]
        )
        # 3. บันทึกความจำใหม่
        supabase.table("long_term_memory").insert({"user_id": user_id, "content": user_text, "embedding": current_vec}).execute()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⚙️ กำลังปรับจูนสมอง... ลองทักอีกครั้งนะ\n(Error: {str(e)[:40]})"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        # 4. โหมดอ่านรูป (Vision Mode) กลับมาแล้ว!
        message_content = line_bot_api.get_message_content(event.message.id)
        base64_image = base64.b64encode(message_content.content).decode('utf-8')
        
        response = groq_client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "ช่วยวิเคราะห์รูปนี้อย่างละเอียดที"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📸 ขออภัยครับ ระบบดวงตามีปัญหานิดหน่อย"))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try: handler.handle(body, signature)
    except: abort(400)
    return 'OK'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
