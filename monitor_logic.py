import json
import datetime
from data_fetcher import groq_client, get_advanced_technical, get_margin_data, get_revenue_data, get_institutional_data, get_latest_news

def evaluate_intraday(symbol: str, name: str) -> dict:
    if not groq_client: return {"error": "No Groq Client"}
    
    tech_data = get_advanced_technical(symbol)
    news_data = get_latest_news(symbol, name)
    
    prompt = f"""
    你是一個專精於台股的即時監控機器人。現在是盤中監控模式（不使用盤後資料）。
    請針對 {name} ({symbol}) 的以下資料，判斷是否出現「中、高優先」的異常事件：
    
    【提供資料】
    即時技術面與價量：
    {json.dumps(tech_data, ensure_ascii=False)}
    即時新聞：
    {json.dumps(news_data, ensure_ascii=False)}
    
    【監控規則】
    請檢查是否有：跳空 > 2%、突破/跌破昨高昨低、突破/跌破 20/60/120日高低點、盤中成交量異常放大(大於均量1.5倍)、接近漲停跌停、假突破現象、重大新聞事件。
    若無重大異常，或僅為普通波動，請嚴格回傳這個 JSON：{{"level": "無異常"}}
    
    若有中/高風險異常，請回傳嚴格的 JSON 格式，不要加入其他文字：
    {{
        "level": "中優先" 或 "高優先",
        "category": "技術面異常" 或 "重大事件與新聞",
        "events": "簡短的一句話總結事件",
        "conditions": ["條件1", "條件2"],
        "judgment": "目前異常現象代表什麼",
        "next_observe": ["重點1", "重點2"],
        "confidence": "高" 或 "中" 或 "低"
    }}
    注意：盤中不可推斷法人或融資狀況，必要時在 judgment 中加上「需等盤後法人 / 融資券資料確認」。
    """
    
    try:
        res = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        content = res.choices[0].message.content.strip()
        return json.loads(content)
    except Exception as e:
        print("Intraday AI error:", e)
        return {"error": str(e)}

def evaluate_postmarket(symbol: str, name: str) -> dict:
    import database
    from data_fetcher import get_foreign_holding_ratio, get_investment_trust_ratio, get_disposition_status
    if not groq_client: return {"error": "No Groq Client"}
    
    tech_data = get_advanced_technical(symbol)
    inst_data = get_institutional_data(symbol)
    margin_data = get_margin_data(symbol)
    rev_data = get_revenue_data(symbol)
    news_data = get_latest_news(symbol, name)
    
    foreign_data = get_foreign_holding_ratio(symbol)
    trust_data = get_investment_trust_ratio(symbol)
    disp_data = get_disposition_status(symbol)
    attn_counts = database.get_attention_history_counts(symbol)
    
    prompt = f"""
    你是一個專精於台股的量化監控機器人。現在是盤後統整模式。
    請針對 {name} ({symbol}) 的全方位資料，產出盤後報告：
    
    【提供資料】
    技術面與價量：{json.dumps(tech_data, ensure_ascii=False)}
    籌碼面：{inst_data}
    融資券：{json.dumps(margin_data, ensure_ascii=False)}
    月營收：{json.dumps(rev_data, ensure_ascii=False)}
    新聞：{json.dumps(news_data, ensure_ascii=False)}
    
    外資持股變化：{json.dumps(foreign_data, ensure_ascii=False)}
    投信占股本比例：{json.dumps(trust_data, ensure_ascii=False)}
    處置狀況：{json.dumps(disp_data, ensure_ascii=False)}
    近30日注意股次數：{json.dumps(attn_counts, ensure_ascii=False)}
    
    【監控規則】
    尋找：三大法人連買/轉賣、融資暴增且股價跌、營收創 12 個月新高或 YoY 轉正、價量異常、重大新聞。
    低優先：單一普通訊號。
    中優先：兩個以上有意義訊號 (如放量突破+法人連買)。
    高優先：重大風險或事件 (重大公告、高檔爆量長黑、融資暴增股價跌、注意股)。
    
    【重要：近期處置風險評估】
    請根據注意股次數與處置狀況評估風險等級 (高/中/低)：
    高風險：近10日有5次以上注意，或近30日有10次以上，或已連續2日注意且今日爆量，或明顯接近處置條件。
    中風險：近5日內有2~3次注意，或短線漲幅大且量爆增、週轉率高，或近期剛出關又轉強。
    低風險：近期無注意紀錄，無異常。
    
    若無任何技術、籌碼、基本面異常，且處置風險為低，請嚴格回傳 JSON：{{"level": "無異常"}}
    
    若有異常或處置風險為中/高，請回傳嚴格 JSON 格式：
    {{
        "level": "低優先" 或 "中優先" 或 "高優先",
        "category": "綜合分類",
        "events": "簡短一句話",
        "conditions": ["條件1", "條件2"],
        "judgment": "這個現象代表什麼",
        "risks": "這個訊號可能失敗或反轉的風險",
        "next_observe": ["觀察1", "觀察2"],
        "confidence": "高" 或 "中" 或 "低",
        "disposition_risk": {{
            "level": "高" 或 "中" 或 "低",
            "reason": "觸發依據",
            "approach": "接近的條件",
            "observe": "後續觀察 (文字段落)"
        }},
        "foreign_judgment": "外資持股判斷 (文字)",
        "trust_judgment": "投信籌碼判斷 (文字)"
    }}
    """
    
    try:
        res = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )
        content = res.choices[0].message.content.strip()
        result_json = json.loads(content)
        
        # Inject raw data for Python formatting later
        result_json['_raw'] = {
            'foreign_data': foreign_data,
            'trust_data': trust_data,
            'disp_data': disp_data,
            'attn_counts': attn_counts
        }
        return result_json
    except Exception as e:
        print("Postmarket AI error:", e)
        return {"error": str(e)}

def format_alert_message(data: dict, symbol: str, name: str, is_intraday: bool = True) -> str:
    if data.get("level") == "無異常":
        return f"{name}({symbol}) 今日無重大異常"
    if "error" in data:
        return f"監控錯誤: {data['error']}"
        
    level = data.get("level", "未知")
    cat = data.get("category", "未分類")
    events = data.get("events", "")
    conditions = "\n".join([f"- {c}" for c in data.get("conditions", [])])
    judgment = data.get("judgment", "")
    observe = "\n".join([f"- {o}" for o in data.get("next_observe", [])])
    confidence = data.get("confidence", "未知")
    
    title = f"【盤中提醒｜{level}｜{cat}】" if is_intraday else f"【盤後報告｜{level}｜{cat}】"
    
    now_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"{title}\n"
    msg += f"股票：{name} ({symbol})\n"
    if is_intraday:
        msg += f"時間：{now_str}\n"
    msg += f"事件：{events}\n"
    msg += f"觸發條件：\n{conditions}\n\n"
    msg += f"判斷：\n{judgment}\n\n"
    if not is_intraday and "risks" in data:
        msg += f"可能風險：\n{data['risks']}\n\n"
    msg += f"後續觀察：\n{observe}\n\n"
    msg += f"信心程度：{confidence}"
    
    if not is_intraday and '_raw' in data:
        raw = data['_raw']
        fd = raw['foreign_data']
        td = raw['trust_data']
        dd = raw['disp_data']
        
        d_risk = data.get('disposition_risk', {})
        f_judg = data.get('foreign_judgment', '無')
        t_judg = data.get('trust_judgment', '無')
        
        msg += "\n\n【法人持股與處置風險】\n\n"
        msg += f"股票：{name} {symbol.replace('.TW','')}\n\n"
        
        msg += "外資持股比例：\n"
        if fd.get('has_data'):
            msg += f"- 最新：{fd['latest_ratio']:.2f}%\n"
            msg += f"- 近 5 日變化：{fd['change_5d']:+.2f} 個百分點\n"
            msg += f"- 近 20 日變化：{fd['change_20d']:+.2f} 個百分點\n"
        else:
            msg += "- 資料不足\n"
        msg += f"- 判斷：{f_judg}\n\n"
        
        msg += "投信籌碼變化：\n"
        if td.get('has_data'):
            msg += f"- 近 5 日投信買賣超占股本：{td['ratio_5d']:+.2f}%\n"
            msg += f"- 近 20 日投信買賣超占股本：{td['ratio_20d']:+.2f}%\n"
            if td['consecutive']: msg += f"- 連買 / 連賣狀況：{td['consecutive']}\n"
            else: msg += "- 連買 / 連賣狀況：無\n"
        else:
            msg += "- 資料不足\n"
        msg += f"- 判斷：{t_judg}\n"
        msg += "- 備註：此為投信買賣超占股本比例，非實際投信持股比例。\n\n"
        
        msg += "處置狀況：\n"
        msg += f"- 目前是否處置中：{dd['is_punished']}\n"
        msg += f"- 處置期間：{dd['period']}\n"
        msg += f"- 處置原因：{dd['reason']}\n"
        msg += f"- 處置措施：{dd['measures']}\n"
        msg += f"- 距離出關：{dd['days_left']}\n"
        msg += f"- 預計出關日：{dd['end_date']}\n\n"
        
        msg += "近期處置風險：\n"
        msg += f"- 風險等級：{d_risk.get('level', '未知')}\n"
        msg += f"- 觸發依據：{d_risk.get('reason', '無')}\n"
        msg += f"- 接近的條件：{d_risk.get('approach', '無')}\n"
        msg += f"- 後續觀察：\n  {d_risk.get('observe', '無')}"
        
    return msg
