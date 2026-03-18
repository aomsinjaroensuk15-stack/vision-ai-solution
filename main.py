import os, base64, hashlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from groq import Groq
from supabase import create_client

app = Flask(__name__)

# --- [CONFIG] ---
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
groq_client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# ฟังก์ชันสร้างพิกัดเสถียร
def get_stable_vector(text):
    h = hashlib.sha256(text.encode()).digest()
    return [float((h[i % len(h)] / 255.0) * 2 - 1) for i in range(1024)]

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"Error in callback: {e}")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    try:
        current_vec = get_stable_vector(user_text)
        # ดึงความจำ
        memories = supabase.rpc("match_memories", {
            "query_embedding": current_vec, "match_threshold": 0.2, "match_count": 3, "p_user_id": user_id
        }).execute()
        context = "\n".join([m['content'] for m in memories.data]) if memories.data else "ไม่มีข้อมูลเก่า"

        # AI Response
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"คุณคือ Sovereign AI ข้อมูลในอดีต: {context}"},
                {"role": "user", "content": user_text}
            ]
        )
        # บันทึกความจำ
        supabase.table("long_term_memory").insert({"user_id": user_id, "content": user_text, "embedding": current_vec}).execute()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🧠 Memory Error: {str(e)[:50]}"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        # 📸 ดึงรูปจาก LINE
        message_content = line_bot_api.get_message_content(event.message.id)
        # แปลงเป็น Base64
        image_data = base64.b64encode(message_content.content).decode('utf-8')
        
        # ส่งให้ Vision Model
        response = groq_client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "วิเคราะห์รูปนี้อย่างละเอียดในฐานะผู้ช่วยอัจฉริยะ"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                    ]
                }
            ]
        )
        ans = response.choices[0].message.content
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"👁️ Vision Analysis:\n{ans}"))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📸 Vision Error: {str(e)[:50]}"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
