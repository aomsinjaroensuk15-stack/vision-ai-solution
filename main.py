import os
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = FastAPI()

# เชื่อมต่อกุญแจ Gemini ที่คุณใส่ใน Render ไว้
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# เชื่อมต่อกับ LINE
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

@app.get("/")
def root():
    return {"message": "Vision AI Brain is Online!"}

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()
    try:
        handler.handle(body.decode('utf-8'), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    try:
        # ส่งข้อความไปให้ Gemini ช่วยคิดคำตอบ
        response = model.generate_content(user_text)
        ai_answer = response.text
        
        # ส่งคำตอบจาก AI กลับไปหาคุณใน LINE
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=ai_answer)
        )
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="ขออภัยครับ สมองขัดข้องนิดหน่อย ลองใหม่อีกทีนะ!")
        )
