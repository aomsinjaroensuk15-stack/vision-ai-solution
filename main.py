import os, httpx, time
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from groq import Groq
from supabase import create_client

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
groq_client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# สร้าง Vector หลอกที่ 'โครงสร้างเป๊ะ' สำหรับ Supabase
# (1024 มิติ ตามที่เราตั้งไว้ใน SQL)
dummy_vector = [0.1] * 1024

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text
    
    try:
        # 1. ค้นหาความจำ (RPC Match Memories)
        # ลองค้นหาดูก่อนว่าเคยคุยอะไรที่คล้ายกันไหม
        memories = supabase.rpc("match_memories", {
            "query_embedding": dummy_vector,
            "match_threshold": 0.4,
            "match_count": 3,
            "p_user_id": user_id
        }).execute()

        context = ""
        if memories.data:
            context = "\n".join([f"อดีต: {m['content']}" for m in memories.data])

        # 2. ให้ AI ตอบโดยใช้ Context (Llama-3.3-70B)
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"คุณคือ Sovereign AI ที่มีความจำยาวนาน ข้อมูลในอดีตที่พบ:\n{context}"},
                {"role": "user", "content": user_text}
            ]
        )
        reply_text = completion.choices[0].message.content

        # 3. บันทึกความจำใหม่ (สำคัญมาก: ต้องบันทึกให้สำเร็จ)
        supabase.table("long_term_memory").insert({
            "user_id": user_id,
            "content": user_text,
            "embedding": dummy_vector
        }).execute()

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    except Exception as e:
        # ถ้าพัง ให้บอทคายสาเหตุออกมาทาง LINE เลยครับ!
        error_msg = f"⚠ System Error: {str(e)[:100]}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=error_msg))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
