import os
import uvicorn
import asyncio
import scheduler_task
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from dotenv import load_dotenv
from bot_logic import handle_user_message

# 載入環境變數
load_dotenv()

# 從環境變數讀取 LINE Bot 的憑證
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "YOUR_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "YOUR_CHANNEL_ACCESS_TOKEN")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)

app = FastAPI(title="LINE Stock Bot")

@app.on_event("startup")
async def startup_event():
    import asyncio
    import scheduler_task
    asyncio.create_task(scheduler_task.scheduler_loop())
    print("Background scheduler started!")

from fastapi import BackgroundTasks

async def process_and_reply(event, user_id, user_text):
    """在背景處理使用者訊息並回覆，避免阻塞主線程"""
    try:
        async with AsyncApiClient(configuration) as api_client:
            line_bot_api = AsyncMessagingApi(api_client)
            
            is_long_task = user_text.startswith("測試") or user_text.startswith("查詢")
            
            if is_long_task:
                # 立即回覆讓 LINE 伺服器知道我們有收到
                try:
                    await line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="⏳ AI 正在為您搜集資料並分析，請稍候約 30 ~ 60 秒...")]
                        )
                    )
                except Exception as e:
                    print(f"Reply hint error: {e}", flush=True)
                
                # 在背景處理
                messages = await asyncio.to_thread(handle_user_message, user_id, user_text)
                
                # 處理完畢後使用 push message 傳送
                try:
                    await line_bot_api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=messages
                        )
                    )
                except Exception as e:
                    print(f"Push message error: {e}", flush=True)
            else:
                # 一般指令直接處理並回覆
                messages = await asyncio.to_thread(handle_user_message, user_id, user_text)
                await line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=messages
                    )
                )
    except Exception as e:
        print(f"Background process error: {e}", flush=True)

@app.post("/callback")
async def handle_callback(request: Request, background_tasks: BackgroundTasks):
    """處理 LINE 伺服器傳來的 Webhook 請求"""
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        events = parser.parse(body_str, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue
        
        # LINE Verify 會傳送無效的 reply_token，直接略過不處理
        if event.reply_token == "00000000000000000000000000000000" or event.reply_token == "ffffffffffffffffffffffffffffffff":
            continue
            
        user_id = event.source.user_id
        user_text = event.message.text
        
        # 將處理與回覆工作交給背景任務
        background_tasks.add_task(process_and_reply, event, user_id, user_text)

    return "OK"

@app.get("/")
def root():
    return {"status": "running"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8080, access_log=False)
