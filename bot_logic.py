from linebot.v3.messaging import (
    TextMessage,
    FlexMessage,
    FlexContainer
)
from data_fetcher import get_stock_price, get_company_info_and_financials, get_ai_investment_report, get_latest_news, get_technical_and_pe, get_institutional_data
import database
import json
from monitor_logic import evaluate_intraday, evaluate_postmarket, format_alert_message

def handle_user_message(user_id: str, text: str) -> list:
    """處理使用者訊息並回傳對應的 LINE Message 物件列表"""
    text = text.strip()
    
    if text == '測試盤中監控':
        stocks = database.get_tracked_stocks(user_id)
        if not stocks: return [TextMessage(text='您尚未追蹤任何股票。請先輸入：新增 2330.TW')]
        reply_texts = []
        for sym in stocks:
            info = get_company_info_and_financials(sym)
            name = info.get('name', sym)
            res = evaluate_intraday(sym, name)
            if res.get('level') != '無異常':
                reply_texts.append(format_alert_message(res, sym, name, True))
        if not reply_texts:
            return [TextMessage(text='✅ 測試完成，您的追蹤清單目前無盤中重大異常。')]
        return [TextMessage(text=t) for t in reply_texts[:5]]

    if text == '測試盤後報告':
        stocks = database.get_tracked_stocks(user_id)
        if not stocks: return [TextMessage(text='您尚未追蹤任何股票。請先輸入：新增 2330.TW')]
        reply_texts = []
        for sym in stocks:
            info = get_company_info_and_financials(sym)
            name = info.get('name', sym)
            res = evaluate_postmarket(sym, name)
            if res.get('level') != '無異常':
                reply_texts.append(format_alert_message(res, sym, name, False))
        if not reply_texts:
            return [TextMessage(text='✅ 測試完成，您的追蹤清單今日無盤後重大異常。')]
        return [TextMessage(text=t) for t in reply_texts[:5]]
        
    if text.startswith(("追蹤", "+", "新增")):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return [TextMessage(text="請提供要追蹤的股票代碼，例如：『追蹤 2330.TW』或『+ AAPL』")]
        symbol = parts[1].strip().upper()
        success, msg = database.add_tracked_stock(user_id, symbol)
        return [TextMessage(text=msg)]
        
    elif text.startswith(("取消追蹤", "-", "移除")):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return [TextMessage(text="請提供要取消追蹤的股票代碼，例如：『取消追蹤 2330.TW』或『- AAPL』")]
        symbol = parts[1].strip().upper()
        success, msg = database.remove_tracked_stock(user_id, symbol)
        return [TextMessage(text=msg)]
        
    elif text == "我的追蹤":
        stocks = database.get_tracked_stocks(user_id)
        if not stocks:
            return [TextMessage(text="您目前沒有追蹤任何股票。請使用『追蹤 [代碼]』來新增。")]
        return [TextMessage(text="您的追蹤名單：\n" + "\n".join(stocks) + "\n\n您可以輸入『查詢 [代碼]』來查看最新資訊。")]
        
    elif text.startswith("查詢"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return [TextMessage(text="請提供要查詢的股票代碼，例如：『查詢 AAPL』")]
        symbol = parts[1].strip().upper()
        return generate_stock_report(symbol)
        
    elif text.upper() == "HELP" or text == "幫助" or text == "說明":
        help_text = (
            "歡迎使用智能股票助理！🤖\n\n"
            "⚠️ 【股票代碼輸入規則】\n"
            "• 美股：直接輸入 (例: AAPL, NVDA)\n"
            "• 台股上市：需加 .TW (例: 2330.TW)\n"
            "• 台股上櫃：需加 .TWO (例: 6173.TWO)\n"
            "*(指令與代碼之間請加一個空白)*\n\n"
            "📌 【可用指令】\n"
            "1. 追蹤 [代碼]：新增追蹤名單\n"
            "2. 取消追蹤 [代碼]：移除追蹤\n"
            "3. 我的追蹤：檢視目前清單\n"
            "4. 查詢 [代碼]：取得即時股價與 AI 健檢\n"
            "5. 測試盤中監控：執行盤中異常掃描\n"
            "6. 測試盤後報告：執行盤後 AI 籌碼解析"
        )
        return [TextMessage(text=help_text)]
        
    else:
        # 預設行為：如果輸入看起來像股票代碼，直接查詢
        if len(text) <= 8 and text.replace(".", "").isalnum():
             return generate_stock_report(text.upper())
        return [TextMessage(text="我不太明白您的意思。請輸入『幫助』查看可用指令。")]

def generate_stock_report(symbol: str) -> list:
    """產生包含股價、AI 基本面解析、雙語新聞的 Flex Message 輪播 (Carousel)"""
    price_data = get_stock_price(symbol)
    if "error" in price_data:
        return [TextMessage(text=f"無法獲取股價資訊：{price_data['error']}")]
        
    info_data = get_company_info_and_financials(symbol)
    company_name = info_data.get('name', price_data['name'])
    
    tech_data = get_technical_and_pe(symbol)
    inst_data = get_institutional_data(symbol)
    
    def format_ai_text(data):
        if isinstance(data, str):
            return data
        elif isinstance(data, list):
            return "\n".join(str(v) for v in data)
        elif isinstance(data, dict):
            return "\n".join(f"[{k}] {v}" if not isinstance(v, list) else f"[{k}]\n" + "\n".join(str(item) for item in v) for k, v in data.items())
        return str(data)

    ai_report = get_ai_investment_report(company_name, symbol, tech_data, inst_data)
    ai_profile = format_ai_text(ai_report.get("profile", "無深度解析資料"))
    ai_advice = format_ai_text(ai_report.get("advice", "無投資建議資料"))
    
    news_data = get_latest_news(symbol, company_name)

    # 判斷漲跌顏色
    color = "#FF0000" if price_data['change'] > 0 else "#00B050" if price_data['change'] < 0 else "#000000"
    sign = "+" if price_data['change'] > 0 else ""
    price_str = f"{price_data['price']:.2f}"
    change_str = f"{sign}{price_data['change']:.2f} ({sign}{price_data['change_percent']:.2f}%)"

    # --- Bubble 1: 即時報價與基本數據 ---
    bubble1 = {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box", "layout": "vertical",
            "contents": [
                {"type": "text", "text": f"{company_name}", "weight": "bold", "size": "xl", "color": "#1DB446", "wrap": True},
                {"type": "text", "text": f"({symbol}) 即時報價", "size": "sm", "color": "#aaaaaa"}
            ]
        },
        "hero": {
            "type": "box", "layout": "vertical", "paddingAll": "md",
            "contents": [
                {"type": "text", "text": price_str, "size": "4xl", "weight": "bold", "align": "center"},
                {"type": "text", "text": change_str, "size": "md", "color": color, "align": "center", "weight": "bold"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "text", "text": "市場數據", "weight": "bold", "size": "md", "margin": "md"},
                {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                    {"type": "text", "text": "板塊", "color": "#aaaaaa", "size": "sm", "flex": 2},
                    {"type": "text", "text": str(info_data.get('sector', '-')), "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
                ]},
                {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                    {"type": "text", "text": "本益比", "color": "#aaaaaa", "size": "sm", "flex": 2},
                    {"type": "text", "text": str(info_data.get('trailing_pe', '-')), "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
                ]},
                {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                    {"type": "text", "text": "EPS", "color": "#aaaaaa", "size": "sm", "flex": 2},
                    {"type": "text", "text": str(info_data.get('eps', '-')), "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
                ]}
            ]
        }
    }

    # --- Bubble 2: AI 深度解析 ---
    bubble2 = {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box", "layout": "vertical",
            "contents": [
                {"type": "text", "text": "AI 深度解析", "weight": "bold", "size": "xl", "color": "#1DB446"},
                {"type": "text", "text": "由 Groq Llama 3 產生", "size": "xs", "color": "#aaaaaa"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "text", "text": ai_profile, "wrap": True, "size": "sm", "color": "#333333", "weight": "regular"}
            ]
        }
    }

    # --- Bubble 3: 雙語新聞 ---
    news_contents = [
        {"type": "text", "text": "最新雙語新聞", "weight": "bold", "size": "xl", "color": "#1DB446", "margin": "md"}
    ]
    
    if isinstance(news_data, list) and len(news_data) > 0:
        for news in news_data:
            lang_label = "🇹🇼" if news["lang"] == "zh" else "🇺🇸"
            news_box = {
                "type": "box",
                "layout": "vertical",
                "margin": "lg",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{lang_label} {news['title']}",
                        "size": "sm",
                        "wrap": True,
                        "color": "#111111",
                        "weight": "bold"
                    },
                    {
                        "type": "text",
                        "text": f"{news['publisher']} - {news['timestamp']}",
                        "size": "xs",
                        "color": "#aaaaaa",
                        "margin": "sm"
                    }
                ],
                "action": {
                    "type": "uri",
                    "label": "action",
                    "uri": news["link"] if news["link"] else "https://finance.yahoo.com/"
                }
            }
            news_contents.append(news_box)
    else:
        news_contents.append({"type": "text", "text": "暫無相關新聞", "size": "sm", "color": "#aaaaaa"})

    bubble3 = {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": news_contents
        }
    }

    # --- Bubble 4: 投資建議 ---
    bubble4 = {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box", "layout": "vertical",
            "contents": [
                {"type": "text", "text": "投資建議 (法人量化邏輯)", "weight": "bold", "size": "xl", "color": "#FF4500"},
                {"type": "text", "text": "由 Groq AI 依據籌碼與月線綜合研判", "size": "xs", "color": "#aaaaaa"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "text", "text": ai_advice, "wrap": True, "size": "sm", "color": "#333333", "weight": "bold"}
            ]
        }
    }

    # 組合成 Carousel
    carousel_json = {
        "type": "carousel",
        "contents": [bubble1, bubble2, bubble4, bubble3]
    }

    flex_container = FlexContainer.from_dict(carousel_json)
    return [FlexMessage(alt_text=f"{company_name} 完整報告", contents=flex_container)]


def generate_news_report(symbol: str) -> list:
    """單獨產生雙語新聞的 Flex Message"""
    
    info_data = get_company_info_and_financials(symbol)
    company_name = info_data.get('name', symbol)
    
    news_data = get_latest_news(symbol, company_name)
    
    news_contents = [
        {"type": "text", "text": f"{company_name} 最新新聞", "weight": "bold", "size": "xl", "color": "#1DB446", "margin": "md", "wrap": True}
    ]
    
    if isinstance(news_data, list) and len(news_data) > 0:
        for news in news_data:
            lang_label = "🇹🇼" if news["lang"] == "zh" else "🇺🇸"
            news_box = {
                "type": "box",
                "layout": "vertical",
                "margin": "lg",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{lang_label} {news['title']}",
                        "size": "sm",
                        "wrap": True,
                        "color": "#111111",
                        "weight": "bold"
                    },
                    {
                        "type": "text",
                        "text": f"{news['publisher']} - {news['timestamp']}",
                        "size": "xs",
                        "color": "#aaaaaa",
                        "margin": "sm"
                    }
                ],
                "action": {
                    "type": "uri",
                    "label": "action",
                    "uri": news["link"] if news["link"] else "https://finance.yahoo.com/"
                }
            }
            news_contents.append(news_box)
    else:
        news_contents.append({"type": "text", "text": "暫無相關新聞", "size": "sm", "color": "#aaaaaa"})

    bubble = {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": news_contents
        }
    }

    flex_container = FlexContainer.from_dict(bubble)
    return [FlexMessage(alt_text=f"{company_name} 最新新聞", contents=flex_container)]
