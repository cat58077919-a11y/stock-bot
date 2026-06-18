# 📈 LINE 智能財經大腦 (AI Stock Assistant)

這是一個基於 FastAPI、LINE Messaging API 與 Llama-3 (Groq) 打造的全自動雲端股票分析機器人。本專案從零開始建置，經歷了從本地端腳本到雲端 24 小時服務的架構演進，並克服了免費雲端主機的各項限制。

## ✨ 核心亮點功能

1. **即時股票健檢 (查詢 [股票代號])**
   - 整合 yfinance 抓取美股/台股即時股價、本益比、營收成長率。
   - 透過 **Groq AI (Llama-3)** 將複雜財報數據轉化為白話文投資建議。
   - 支援台股上市 (.TW) 與上櫃 (.TWO) 後綴。

2. **全自動雙時段排程廣播**
   - **09:00 盤中監控**：即時掃描追蹤清單，偵測價量異常、突破/跌破關鍵價位，以及突發重大外電新聞。
   - **18:30 盤後報告**：自動結算當日籌碼變化（外資/投信買賣超）、營收創高警示，以及處置股追蹤預警。

3. **跨平台多人派發**
   - 除了 LINE Flex Message 精美卡片推播，還支援將盤後報告整理並透過 Email 自動發送給多個註冊信箱。

## ⚙️ 技術堆疊 (Tech Stack)

- **Backend**: Python 3, FastAPI, Uvicorn
- **AI Engine**: Groq API (Llama-3-8b-instant)
- **Database**: PostgreSQL (Neon Serverless) / SQLAlchemy ORM
- **Automation**: APScheduler (時區校正為 Asia/Taipei)
- **Messaging**: LINE Messaging API SDK
- **Data Source**: yfinance, feedparser (Yahoo Finance RSS)
- **Deployment**: Render Web Service + UptimeRobot (防休眠機制)

## 📂 專案架構 (Modular Design)

專案採用高度模組化設計，分為七大核心元件：
- main.py: FastAPI 進入點、LINE Webhook 處理與背景任務分發。
- ot_logic.py: 處理使用者指令路由、產生 Flex Message JSON 版面。
- data_fetcher.py: 負責對外 API 請求（yfinance 爬蟲、新聞 RSS、Groq AI 對話）。
- monitor_logic.py: 存放盤中/盤後監控的判斷邏輯與 AI 觸發條件設定。
- database.py: SQLAlchemy 資料庫連線與 ORM 模型設定 (包含 SSL 斷線重連機制)。
- scheduler_task.py: APScheduler 背景排程迴圈，定時觸發盤中與盤後任務。
- email_sender.py: SMTP 郵件發送模組。
- 
equirements.txt: 雲端主機環境建置相依套件清單。

## ⚠️ 資安與部署聲明

為確保資安，本專案實施嚴格的 .env 環境變數隔離。所有 API Keys (包含 LINE Token、Groq API Key、資料庫連線字串、Email 密碼) 皆存放於雲端主機的環境變數後台，**絕不包含在開源程式碼中**。

---
*Developed with Human-AI Collaboration.*