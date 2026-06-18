import yfinance as yf
from datetime import datetime
import textwrap
import urllib.parse
import feedparser
import groq
import os
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if GROQ_API_KEY:
    groq_client = groq.Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None

import requests
from datetime import timedelta

def get_technical_and_pe(symbol: str) -> dict:
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="6mo")
        if hist.empty: return {}
        
        current_price = float(hist['Close'].iloc[-1])
        ma20 = hist['Close'].rolling(window=20).mean()
        if len(ma20) < 2: return {}
        
        cur_ma20 = float(ma20.iloc[-1])
        prev_ma20 = float(ma20.iloc[-2])
        bias = (current_price - cur_ma20) / cur_ma20 * 100
        slope = "向上" if cur_ma20 > prev_ma20 else "向下"
        
        info = stock.info
        eps_fwd = info.get("forwardEps", "無資料")
        eps_trl = info.get("trailingEps", "無資料")
        pe_fwd = info.get("forwardPE", "無資料")
        pe_trl = info.get("trailingPE", "無資料")
        
        # 抓取大投信/機構持股比例 (主要給美股用)
        inst_holdings = info.get("heldPercentInstitutions", 0)
        if inst_holdings:
            inst_holdings = f"{inst_holdings * 100:.2f}%"
        else:
            inst_holdings = "無資料"
        
        return {
            "price": current_price,
            "ma20": cur_ma20,
            "bias": bias,
            "slope": slope,
            "eps_forward": eps_fwd,
            "eps_trailing": eps_trl,
            "pe_forward": pe_fwd,
            "pe_trailing": pe_trl,
            "inst_holdings": inst_holdings
        }
    except Exception as e:
        print("get_technical_and_pe error:", e)
        return {}

def get_institutional_data(symbol: str) -> str:
    if not (symbol.endswith(".TW") or symbol.endswith(".TWO")):
        return "非台股，不適用台灣投信/外資資料。請參考基本面的大機構持股比例。"
        
    try:
        code = symbol.split(".")[0]
        url = "https://api.finmindtrade.com/api/v4/data"
        start_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
        
        res = requests.get(url, params={
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": code,
            "start_date": start_date
        }).json()
        
        if "data" not in res or not res["data"]:
            return "近期無籌碼資料"
            
        data = res["data"]
        # 取最近 5 個交易日
        dates = sorted(list(set(d["date"] for d in data)))[-5:]
        summary = []
        for d in dates:
            f_buy = sum(item["buy"] - item["sell"] for item in data if item["date"] == d and item["name"] == "Foreign_Investor")
            t_buy = sum(item["buy"] - item["sell"] for item in data if item["date"] == d and item["name"] == "Investment_Trust")
            summary.append(f"{d}: 外資淨買賣 {f_buy/1000:.1f}張, 投信淨買賣 {t_buy/1000:.1f}張")
            
        return "\n".join(summary)
    except Exception as e:
        print("get_institutional_data error:", e)
        return "籌碼資料獲取失敗"

def get_stock_price(symbol: str) -> dict:
    """獲取最新股價資訊"""
    try:
        stock = yf.Ticker(symbol)
        history = stock.history(period="1d")
        if history.empty:
            return {"error": f"找不到股票代碼 {symbol} 的資料"}
        
        current_price = history['Close'].iloc[0]
        history_5d = stock.history(period="5d")
        if len(history_5d) >= 2:
            prev_close = history_5d['Close'].iloc[-2]
            change = current_price - prev_close
            change_percent = (change / prev_close) * 100
        else:
            prev_close = stock.info.get('previousClose', current_price)
            change = current_price - prev_close
            change_percent = (change / prev_close) * 100 if prev_close else 0

        info = stock.info
        name = info.get('shortName', symbol)
        currency = info.get('currency', '')

        return {
            "symbol": symbol,
            "name": name,
            "price": current_price,
            "change": change,
            "change_percent": change_percent,
            "currency": currency,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {"error": str(e)}

def get_company_info_and_financials(symbol: str) -> dict:
    """獲取公司基本資訊與財報摘要"""
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        
        if not info:
            return {"error": f"找不到股票代碼 {symbol} 的公司資訊"}

        return {
            "symbol": symbol,
            "name": info.get('shortName', symbol),
            "sector": info.get('sector', '未知板塊'),
            "industry": info.get('industry', '未知產業'),
            "market_cap": info.get('marketCap', '未知'),
            "trailing_pe": info.get('trailingPE', '無資料'),
            "forward_pe": info.get('forwardPE', '無資料'),
            "eps": info.get('trailingEps', '無資料'),
            "dividend_yield": info.get('dividendYield', 0)
        }
    except Exception as e:
        return {"error": str(e)}

import json

def get_ai_investment_report(company_name: str, symbol: str, tech_data: dict, inst_data: str) -> dict:
    if not groq_client:
        return {"profile": "尚未設定 Groq API Key，無法產生 AI 深度解析。", "advice": "尚未設定 Groq API Key，無法產生投資建議。"}
        
    try:
        tech_str = json.dumps(tech_data, ensure_ascii=False)
        prompt = f"""
        你是一位專業的華爾街量化操盤手與金融分析師，精通繁體中文。請針對 {company_name} ({symbol}) 提供 JSON 格式的報告。

        【資料提供】
        基本面與技術面資料：{tech_str}
        籌碼面資料 (每日外資/投信淨買賣張數)：
        {inst_data}

        【任務要求】
        請回傳一個嚴格的 JSON 物件，包含以下兩個欄位：

        1. "profile" (公司深度解析，約 250 字)：
           - 他做的東西是幹嘛的，最近有甚麼新議題會使他的重要性攀升？
           - 競爭對手有誰，市占率大約是多少？
           - 接下來各個業務的營收占比預估？
           - 請用條列式、易讀的排版。

        2. "advice" (投資建議，約 250 字)：
           根據以下邏輯與提供的資料，給出投資建議：
           - **基本面**：分析法人預估的今年/明年 EPS (eps_trailing vs eps_forward)，以及本益比區間 (pe_trailing vs pe_forward)。
           - **籌碼面**：
             * 對於台股：若投信連續買超 > 3 天且遞增 -> 「動能強(加分)」。若外資與投信「同買」 -> 「共識極強(大加分)」。若法人由買轉賣連續 2 天 -> 「警示(準備獲利了結)」。
             * 對於美股：根據大機構持股比例 (inst_holdings) 來判斷法人參與度。
           - **技術面**：
             * 趨勢判定：若股價 > 20MA 且 20MA 斜率向上 -> 「多頭格局(允許做多)」。
             * 進出點風險：若股價大於 20MA 且乖離率 (bias) 超過 10% 到 15% -> 觸發「乖離過大」警示，建議等待拉回，禁止盲目追高。若股價回踩 20MA 且不破 -> 發出「買進訊號」。
           - 請將分析邏輯清晰地條列出來，並給出明確的【結論】(如：買進、觀望、獲利了結等)。

        【極度重要警告】
        請注意，"profile" 與 "advice" 這兩個欄位的值必須是單一的純文字字串 (String)。如果你要條列，請在字串內使用換行符號 (\\n)。絕對不可以讓 "profile" 或 "advice" 變成巢狀字典 (Nested Object) 或陣列 (Array)！

        請務必只回傳 JSON，不要加上 markdown code blocks (例如 ```json)，直接輸出 {{ ... }}。
        """
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.5,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )
        result = response.choices[0].message.content.strip()
        return json.loads(result)
    except Exception as e:
        print("get_ai_investment_report error:", e)
        return {"profile": f"AI 解析產生失敗：{str(e)}", "advice": f"投資建議產生失敗：{str(e)}"}

def get_latest_news(symbol: str, company_name: str) -> list:
    """獲取中英文最新相關新聞"""
    results = []
    
    # 1. 抓取中文新聞 (透過 Google News RSS)
    try:
        search_term = company_name
        if symbol.endswith(".TW") or symbol.endswith(".TWO"):
            search_term = symbol.split(".")[0] # 台股用代碼搜尋比較準確，例如 2330
            
        query = urllib.parse.quote(f"{search_term} 股票")
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries[:3]: # 取前 3 則中文
            results.append({
                "title": entry.title,
                "publisher": entry.source.title if hasattr(entry, 'source') else "Google News",
                "link": entry.link,
                "timestamp": entry.published[5:22] if hasattr(entry, 'published') else "未知時間",
                "lang": "zh"
            })
    except Exception as e:
        print(f"Fetch Chinese news error: {e}")

    # 2. 抓取英文新聞 (透過 yfinance)
    try:
        stock = yf.Ticker(symbol)
        news_list = stock.news
        for news in news_list[:2]: # 取前 2 則英文
            content = news.get("content", news)
            title = content.get("title", news.get("title", "無標題"))
            publisher = content.get("provider", {}).get("displayName", news.get("publisher", "未知來源"))
            
            link = ""
            if "clickThroughUrl" in content and content["clickThroughUrl"]:
                 link = content["clickThroughUrl"].get("url", "")
            elif "canonicalUrl" in content and content["canonicalUrl"]:
                 link = content["canonicalUrl"].get("url", "")
            else:
                 link = news.get("link", "")
                 
            pub_date = content.get("pubDate")
            if pub_date:
                timestamp_str = pub_date.replace("T", " ")[:16]
            else:
                provider_time = news.get("providerPublishTime", 0)
                timestamp_str = datetime.fromtimestamp(provider_time).strftime("%Y-%m-%d %H:%M") if provider_time else "未知時間"

            results.append({
                "title": title,
                "publisher": publisher,
                "link": link,
                "timestamp": timestamp_str,
                "lang": "en"
            })
    except Exception as e:
         print(f"Fetch English news error: {e}")

    return results

if __name__ == "__main__":
    # 測試
    print("測試 2330.TW:")
    info = get_company_info_and_financials("2330.TW")
    print(info)
    print("\nAI 解析:")
    print(get_ai_investment_report(info.get('name', 'TSMC'), "2330.TW", {}, ""))
    print("\n新聞:")
    news = get_latest_news("2330.TW", info.get('name', '台積電'))
    for n in news:
         print(f"[{n['lang']}] {n['title']}")


def get_margin_data(symbol: str) -> dict:
    if not (symbol.endswith('.TW') or symbol.endswith('.TWO')):
        return {}
    try:
        code = symbol.split('.')[0]
        url = 'https://api.finmindtrade.com/api/v4/data'
        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        res = requests.get(url, params={'dataset': 'TaiwanStockMarginPurchaseShortSale', 'data_id': code, 'start_date': start_date}).json()
        data = res.get('data', [])
        if not data: return {}
        # Get last 2 days
        recent = data[-2:]
        if len(recent) < 2: return {}
        today_data = recent[-1]
        yesterday_data = recent[-2]
        
        margin_diff = today_data['MarginPurchaseTodayBalance'] - yesterday_data['MarginPurchaseTodayBalance']
        margin_pct = (margin_diff / yesterday_data['MarginPurchaseTodayBalance'] * 100) if yesterday_data['MarginPurchaseTodayBalance'] > 0 else 0
        
        short_diff = today_data['ShortSaleTodayBalance'] - yesterday_data['ShortSaleTodayBalance']
        
        return {
            'margin_diff': margin_diff,
            'margin_pct': margin_pct,
            'short_diff': short_diff,
            'margin_balance': today_data['MarginPurchaseTodayBalance'],
            'short_balance': today_data['ShortSaleTodayBalance']
        }
    except Exception as e:
        print('margin data error:', e)
        return {}

def get_revenue_data(symbol: str) -> dict:
    if not (symbol.endswith('.TW') or symbol.endswith('.TWO')):
        return {}
    try:
        code = symbol.split('.')[0]
        url = 'https://api.finmindtrade.com/api/v4/data'
        start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
        res = requests.get(url, params={'dataset': 'TaiwanStockMonthRevenue', 'data_id': code, 'start_date': start_date}).json()
        data = res.get('data', [])
        if not data: return {}
        
        latest = data[-1]
        # Check YoY
        # Find same month last year
        last_year_data = next((d for d in data if d['revenue_year'] == latest['revenue_year'] - 1 and d['revenue_month'] == latest['revenue_month']), None)
        yoy = ((latest['revenue'] - last_year_data['revenue']) / last_year_data['revenue'] * 100) if last_year_data and last_year_data['revenue'] > 0 else 0
        
        # Check if 12 month high
        last_12 = [d['revenue'] for d in data[-12:]]
        is_12m_high = len(last_12) > 0 and latest['revenue'] == max(last_12)
        
        return {
            'latest_revenue': latest['revenue'],
            'yoy': yoy,
            'is_12m_high': is_12m_high
        }
    except Exception as e:
        print('revenue data error:', e)
        return {}

def get_advanced_technical(symbol: str) -> dict:
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period='1y')
        if hist.empty: return {}
        
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        vol = hist['Volume']
        
        cur_price = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) > 1 else float(cur_price)
        prev_high = float(high.iloc[-2]) if len(high) > 1 else float(cur_price)
        prev_low = float(low.iloc[-2]) if len(low) > 1 else float(cur_price)
        
        ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
        ma60 = float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else None
        ma120 = float(close.rolling(120).mean().iloc[-1]) if len(close) >= 120 else None
        
        high20 = float(high.rolling(20).max().iloc[-2]) if len(high) >= 20 else None
        low20 = float(low.rolling(20).min().iloc[-2]) if len(low) >= 20 else None
        high60 = float(high.rolling(60).max().iloc[-2]) if len(high) >= 60 else None
        low60 = float(low.rolling(60).min().iloc[-2]) if len(low) >= 60 else None
        
        vol_avg_20 = float(vol.rolling(20).mean().iloc[-2]) if len(vol) >= 20 else None
        cur_vol = float(vol.iloc[-1])
        
        gap_pct = float(((hist['Open'].iloc[-1] - prev_close) / prev_close * 100) if prev_close > 0 else 0)
        
        return {
            'price': cur_price,
            'prev_close': prev_close,
            'prev_high': prev_high,
            'prev_low': prev_low,
            'ma20': ma20,
            'ma60': ma60,
            'ma120': ma120,
            'high20': high20,
            'low20': low20,
            'high60': high60,
            'low60': low60,
            'vol_avg_20': vol_avg_20,
            'cur_vol': cur_vol,
            'gap_pct': gap_pct
        }
    except Exception as e:
        print('technical data error:', e)
        return {}


def sync_attention_stocks():
    import requests
    from datetime import datetime
    import database
    
    url = 'https://openapi.twse.com.tw/v1/exchangeReport/TWTB4U'
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            now_str = datetime.now().strftime('%Y-%m-%d')
            for item in data:
                code = item.get('Code')
                if code:
                    database.record_attention_stock(code, now_str)
                    database.record_attention_stock(code + '.TW', now_str)
            print(f'Synced {len(data)} attention stocks from TWSE for {now_str}')
    except Exception as e:
        print('Error syncing attention stocks:', e)

def get_foreign_holding_ratio(symbol: str) -> dict:
    import requests
    from datetime import datetime, timedelta
    stock_id = symbol.split('.')[0]
    url = 'https://api.finmindtrade.com/api/v4/data'
    start_date = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
    params = {
        'dataset': 'TaiwanStockShareholding',
        'data_id': stock_id,
        'start_date': start_date
    }
    
    result = {
        'latest_ratio': 0.0,
        'change_5d': 0.0,
        'change_20d': 0.0,
        'has_data': False
    }
    try:
        res = requests.get(url, params=params, timeout=10).json()
        data = res.get('data', [])
        if data and len(data) > 0:
            result['has_data'] = True
            latest = float(data[-1].get('ForeignInvestmentSharesRatio', 0))
            result['latest_ratio'] = latest
            
            if len(data) >= 6:
                past_5 = float(data[-6].get('ForeignInvestmentSharesRatio', latest))
                result['change_5d'] = round(latest - past_5, 2)
            else:
                past_first = float(data[0].get('ForeignInvestmentSharesRatio', latest))
                result['change_5d'] = round(latest - past_first, 2)
                
            if len(data) >= 21:
                past_20 = float(data[-21].get('ForeignInvestmentSharesRatio', latest))
                result['change_20d'] = round(latest - past_20, 2)
            else:
                past_first = float(data[0].get('ForeignInvestmentSharesRatio', latest))
                result['change_20d'] = round(latest - past_first, 2)
    except Exception as e:
        print('Error fetching foreign holding:', e)
        
    return result

def get_investment_trust_ratio(symbol: str) -> dict:
    import requests
    import yfinance as yf
    from datetime import datetime, timedelta
    stock_id = symbol.split('.')[0]
    url = 'https://api.finmindtrade.com/api/v4/data'
    
    result = {
        'ratio_5d': 0.0,
        'ratio_20d': 0.0,
        'consecutive': '',
        'has_data': False
    }
    
    try:
        # Get outstanding shares using yfinance
        try:
            ticker = yf.Ticker(symbol)
            shares = ticker.info.get('sharesOutstanding', 0)
        except Exception as e:
            print("yfinance failed to get shares:", e)
            shares = 0
            
        if shares == 0:
            # Fallback to a hardcoded logic or just return
            return result
            
        result['has_data'] = True
        
        # Get investment trust buy/sell
        start_date = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
        res_inst = requests.get(url, params={
            'dataset': 'TaiwanStockInstitutionalInvestorsBuySell',
            'data_id': stock_id,
            'start_date': start_date
        }, timeout=10).json()
        inst_data = res_inst.get('data', [])
        
        trust_data = [d for d in inst_data if d.get('name') == '投信' or d.get('name') == 'Investment_Trust']
        
        if trust_data:
            recent_20 = trust_data[-20:]
            recent_5 = trust_data[-5:]
            
            sum_5 = sum(d.get('buy', 0) - d.get('sell', 0) for d in recent_5)
            sum_20 = sum(d.get('buy', 0) - d.get('sell', 0) for d in recent_20)
            
            result['ratio_5d'] = round((sum_5 / shares) * 100, 2)
            result['ratio_20d'] = round((sum_20 / shares) * 100, 2)
            
            # Consecutive logic
            consecutive = 0
            is_buy = True
            for d in reversed(trust_data):
                net = d.get('buy', 0) - d.get('sell', 0)
                if consecutive == 0:
                    if net > 0: is_buy = True
                    elif net < 0: is_buy = False
                    else: break
                    consecutive = 1
                else:
                    if (net > 0 and is_buy) or (net < 0 and not is_buy):
                        consecutive += 1
                    else:
                        break
                        
            if consecutive >= 5:
                action_str = '買' if is_buy else '賣'
                result['consecutive'] = f'投信連{action_str} {consecutive} 日'
                
    except Exception as e:
        print('Error fetching trust ratio:', e)
        
    return result

def get_disposition_status(symbol: str) -> dict:
    import requests
    import re
    from datetime import datetime, timedelta
    stock_id = symbol.split('.')[0]
    
    result = {
        'is_punished': '否',
        'period': '無',
        'reason': '無',
        'measures': '無',
        'days_left': '不適用',
        'end_date': '不適用'
    }
    
    def parse_measure(t):
        if not t or t == '無': return t
        match = re.search(r'約每(\d+)分鐘', t)
        if match: return f"{match.group(1)}分鐘交易一次"
        match = re.search(r'(\d+)\s*分鐘', t)
        if match: return f"{match.group(1)}分鐘交易一次"
        return t
    
    try:
        url_twse = 'https://openapi.twse.com.tw/v1/announcement/punish'
        res = requests.get(url_twse, timeout=10)
        found = False
        if res.status_code == 200:
            data = res.json()
            for item in data:
                if item.get('Code') == stock_id:
                    result['is_punished'] = '是'
                    result['period'] = item.get('DispositionPeriod', '無')
                    result['reason'] = item.get('ReasonsOfDisposition', '無')
                    result['measures'] = parse_measure(item.get('DispositionMeasures', '無'))
                    found = True
                    break
        
        if not found:
            url_tpex = 'https://www.tpex.org.tw/openapi/v1/tpex_disposal_information'
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            res = requests.get(url_tpex, timeout=10, verify=False)
            if res.status_code == 200:
                data = res.json()
                for item in data:
                    if item.get('SecuritiesCompanyCode') == stock_id:
                        result['is_punished'] = '是'
                        result['period'] = item.get('DispositionPeriod', '無')
                        result['reason'] = item.get('DispositionReasons', '無')
                        result['measures'] = parse_measure(item.get('DisposalCondition', '無'))
                        found = True
                        break
        
        if found:
            period = result['period']
            if '~' in period:
                parts = period.split('~')
                if len(parts) == 2:
                    end_part = parts[1].strip()
                    try:
                        if '/' in end_part:
                            eparts = end_part.split('/')
                            if len(eparts) == 3:
                                y = int(eparts[0]) + 1911
                                m = int(eparts[1])
                                d = int(eparts[2])
                        else:
                            if len(end_part) >= 7:
                                y = int(end_part[:-4]) + 1911
                                m = int(end_part[-4:-2])
                                d = int(end_part[-2:])
                        end_date = datetime(y, m, d)
                        result['end_date'] = end_date.strftime('%Y-%m-%d')
                        
                        now = datetime.now()
                        days_left = 0
                        curr = now + timedelta(days=1)
                        while curr.date() <= end_date.date():
                            if curr.weekday() < 5:
                                days_left += 1
                            curr += timedelta(days=1)
                        result['days_left'] = str(days_left) + ' 個交易日'
                    except Exception as e:
                        print('Date parse error:', e)
                        pass
    except Exception as e:
        print('Error fetching disposition:', e)
        
    return result

