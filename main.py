import os
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = FastAPI()

# เชื่อมต่อกุญแจ
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash')

line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

@app.get("/")
def root():
    return {"status": "online", "key_loaded": api_key is not None}

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
        response = model.generate_content(user_text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.text))
    except Exception as e:
        # บรรทัดนี้จะบอกเราว่า "พังเพราะอะไร" ในหน้า Logs ของ Render ครับ
        print(f"DEBUG ERROR: {str(e)}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"สมองขัดข้อง: {str(e)[:50]}...")
        )
