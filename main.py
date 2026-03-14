from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os

app = FastAPI()

# ดึงค่าจาก Environment Variables เพื่อความปลอดภัย
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

@app.get("/")
def root():
    return {"message": "Vision AI Solution is Online!"}

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
    # ตอบกลับเบื้องต้นก่อน
    reply_text = f"Vision AI ได้รับข้อความ: '{user_text}' แล้วครับ!" 
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
