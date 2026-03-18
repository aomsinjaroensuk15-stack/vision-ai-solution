import os, base64, httpx, time, numpy as np
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from groq import Groq
from supabase import create_client

app = Flask(__name__)

# --- [CORE CONFIG] ---
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
groq_client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# ฟังก์ชันสร้าง Embedding (หัวใจของความยาก X5)
# เราจะใช้โมเดลตัวเล็กของ Groq มาทำหน้าที่เป็น "นักแปลภาษาคนเป็นพิกัด"
def get_embedding(text):
    # ในระดับใช้งานจริง เราจะใช้ Llama-3-8b หรือ API เฉพาะ
    # แต่เพื่อให้ "ฟรีและแรง" เราจะใช้เทคนิคจำลองพิกัดผ่าน AI
    completion = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "system", "content": "Output only 1024 random-seeded numbers based on text, as a list [0.1, ...]"},
                  {"role": "user", "content": text}]
    )
    # หมายเหตุ: ในขั้นสูงเราจะใช้ Embedding Model จริงๆ แต่ตอนนี้เราใช้ Logic AI คุมพิกัดก่อน
    return [0.1] * 1024 # Placeholder: พรุ่งนี้เราจะเปลี่ยนเป็น API จริง

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    
    try:
        # 1. สร้างพิกัดความหมาย (Vector Embedding)
        # embedding = get_embedding(user_text) 

        # 2. ค้นหาความจำที่ "คล้ายกัน" จากลิ้นชักใหม่ (match_memories)
        # เราจะเรียกใช้ RPC ที่คุณเพิ่งสร้างผ่าน SQL!
        memories = supabase.rpc("match_memories", {
            "query_embedding": [0.1]*1024, # พิกัดที่ต้องการหา
            "match_threshold": 0.5,
            "match_count": 3,
            "p_user_id": user_id
        }).execute()

        context = ""
        if memories.data:
            context = "\n".join([m['content'] for m in memories.data])

        # 3. ส่งให้ Llama-3.1-70B (หรือ 405B ถ้าโควต้าเหลือ) ประมวลผล
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"คุณคือ AI ที่มีความจำยาวนาน นี่คืออดีตที่เกี่ยวข้อง:\n{context}"},
                {"role": "user", "content": user_text}
            ]
        )
        
        # 4. บันทึกความจำใหม่ลงตาราง long_term_memory
        supabase.table("long_term_memory").insert({
            "user_id": user_id,
            "content": user_text,
            "embedding": [0.1]*1024 # บันทึกพิกัดไว้ค้นหาคราวหน้า
        }).execute()

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.choices[0].message.content))
        
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🧠 ระบบความจำกำลังจูนพิกัดครับ...\n(Error: {str(e)[:50]})"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
