
import asyncio
import datetime
import os
from database import get_all_users_and_stocks, check_and_record_push
from data_fetcher import get_company_info_and_financials
from monitor_logic import evaluate_intraday, evaluate_postmarket, format_alert_message
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
from email_sender import send_email

async def send_push_message(user_id: str, message: str):
    LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print('Push API token not found.')
        return
        
    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        try:
            push_request = PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=message)]
            )
            line_bot_api.push_message(push_request)
            print(f'Pushed message to {user_id}')
        except Exception as e:
            print(f'Failed to push message: {e}')

async def intraday_job():
    print(f"[{datetime.datetime.now()}] Running intraday scan...")
    # get_all_users_and_stocks is synchronous DB call
    users_data = await asyncio.to_thread(get_all_users_and_stocks)
    for user_id, symbols in users_data.items():
        intraday_alerts = []
        for sym in symbols:
            info = await asyncio.to_thread(get_company_info_and_financials, sym)
            name = info.get("name", sym)
            res = await asyncio.to_thread(evaluate_intraday, sym, name)
            
            if res.get("level") not in ["無異常", "低優先"] and "error" not in res:
                # Deduplication logic (30 mins)
                event_desc = res.get("events", "unknown_event")
                can_push = await asyncio.to_thread(check_and_record_push, user_id, sym, event_desc, 30)
                if can_push:
                    msg = format_alert_message(res, sym, name, is_intraday=True)
                    await send_push_message(user_id, msg)
                    intraday_alerts.append(msg)
                else:
                    print(f"[{sym}] Suppressed due to deduplication: {event_desc}")
                    
        # 將盤中警示打包寄送 Email
        if intraday_alerts:
            email_content = "以下是剛剛為您偵測到的盤中異常警示：\n\n" + "\n\n".join(intraday_alerts)
            await asyncio.to_thread(send_email, "【盤中監控】股票異常警示", email_content)

async def post_market_job():
    print(f"[{datetime.datetime.now()}] Running post-market scan...")
    users_data = await asyncio.to_thread(get_all_users_and_stocks)
    for user_id, symbols in users_data.items():
        summary_messages = []
        for sym in symbols:
            info = await asyncio.to_thread(get_company_info_and_financials, sym)
            name = info.get("name", sym)
            res = await asyncio.to_thread(evaluate_postmarket, sym, name)
            
            if res.get("level") != "無異常" and "error" not in res:
                summary_messages.append(format_alert_message(res, sym, name, is_intraday=False))
        
        if summary_messages:
            # Send up to 5 messages to avoid API limits at once
            for msg in summary_messages[:5]:
                await send_push_message(user_id, msg)
                
            # 將盤後報告打包寄送 Email (包含所有股票)
            email_content = "以下是今日的盤後 AI 解析報告：\n\n" + "\n\n".join(summary_messages)
            await asyncio.to_thread(send_email, "【盤後報告】每日股票 AI 解析", email_content)

async def scheduler_loop():
    # 設定為台灣時間 (UTC+8)，避免 Render 主機預設為 UTC 導致排程時間錯亂
    tz_taipei = datetime.timezone(datetime.timedelta(hours=8))
    while True:
        now = datetime.datetime.now(tz_taipei)
        
        # 只在週一至週五 (weekday 0~4) 執行監控，避免假日休市也去探測
        if now.weekday() < 5:
            # Intraday Scan: 09:00 to 13:30, every 30 minutes
            # Just simple modulo logic: Check if minute is 0 or 30
            if 9 <= now.hour <= 13:
                if now.hour == 13 and now.minute > 30:
                    pass # Market closed
                elif now.minute in [0, 30]:
                    # We use asyncio.create_task so it doesn't block the exact minute check
                    asyncio.create_task(intraday_job())
                    await asyncio.sleep(60) # Wait 1 minute to avoid triggering again in the same minute

            # Post Market Scan: exactly at 18:30
            if now.hour == 18 and now.minute == 30:
                asyncio.create_task(post_market_job())
                await asyncio.sleep(60)
            
        await asyncio.sleep(20) # Check every 20 seconds
