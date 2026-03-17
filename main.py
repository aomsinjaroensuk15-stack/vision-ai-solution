Skip to content
aomsinjaroensuk15-stack
vision-ai-solution
Repository navigation
Code
Issues
Pull requests
Actions
Projects
Wiki
Security
Insights
Settings
Files
Go to file
t
Procfile
README.md
main.py
requirements.txt
vision-ai-solution
/
main.py
in
main

Edit

Preview
Indent mode

Spaces
Indent size

4
Line wrap mode

No wrap
Editing main.py file contents
  1
  2
  3
  4
  5
  6
  7
  8
  9
 10
 11
 12
 13
 14
 15
 16
 17
 18
 19
 20
 21
 22
 23
 24
 25
 26
 27
 28
 29
 30
 31
 32
 33
 34
 35
 36
import os
import base64
import fitz  # PyMuPDF
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage, 
    FileMessage, FlexSendMessage
)
from groq import Groq

app = Flask(__name__)

# ดึงค่าจาก Environment Variables
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

# ระบบจำบทสนทนา (Memory)
user_sessions = {}

def get_chat_history(user_id):
    if user_id not in user_sessions:
        # แก้ปัญหาที่ 1: ตั้งค่าเริ่มต้นแบบเงียบๆ ไม่ทักทายซ้ำซาก
        user_sessions[user_id] = [{"role": "system", "content": "คุณคือ Vision AI Solution ติวเตอร์อัจฉริยะ ตอบคำถามอย่างชาญฉลาดและกระชับ"}]
    return user_sessions[user_id]

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
Use Control + Shift + m to toggle the tab key moving focus. Alternatively, use esc then tab to move to the next interactive element on the page.
