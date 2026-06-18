import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# 優先讀取雲端資料庫網址，若無則使用本地 SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./tracked_stocks.db")

# SQLAlchemy 支援的是 postgresql://，但有些平台會給 postgres://，需要轉換
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite 專屬參數
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# 加入 pool_pre_ping=True 與 pool_recycle=300 以防止雲端資料庫閒置斷線 (SSL connection closed unexpectedly)
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
else:
    engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, pool_recycle=300)
    
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TrackedStock(Base):
    __tablename__ = "tracked_stocks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True) # LINE User ID
    symbol = Column(String, index=True)  # Stock symbol (e.g., AAPL, 2330.TW)
    created_at = Column(DateTime, default=datetime.utcnow)
class PushHistory(Base):
    __tablename__ = "push_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    symbol = Column(String, index=True)
    event_desc = Column(String)
    push_time = Column(DateTime, default=datetime.utcnow)

def check_and_record_push(user_id: str, symbol: str, event_desc: str, cooldown_minutes: int = 30) -> bool:
    from datetime import timedelta
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
        recent_push = db.query(PushHistory).filter(
            PushHistory.user_id == user_id,
            PushHistory.symbol == symbol,
            PushHistory.event_desc == event_desc,
            PushHistory.push_time >= cutoff
        ).first()
        
        if recent_push:
            return False
            
        new_push = PushHistory(user_id=user_id, symbol=symbol, event_desc=event_desc)
        db.add(new_push)
        db.commit()
        return True
    except Exception as e:
        print("PushHistory error:", e)
        db.rollback()
        return True
    finally:
        db.close()
class AttentionStockHistory(Base):
    __tablename__ = "attention_stock_history"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    date_str = Column(String, index=True) # YYYY-MM-DD
    is_attention = Column(Integer, default=1)

def record_attention_stock(symbol: str, date_str: str):
    db = SessionLocal()
    try:
        existing = db.query(AttentionStockHistory).filter(
            AttentionStockHistory.symbol == symbol,
            AttentionStockHistory.date_str == date_str
        ).first()
        if not existing:
            new_record = AttentionStockHistory(symbol=symbol, date_str=date_str)
            db.add(new_record)
            db.commit()
    except Exception as e:
        print("Attention DB error:", e)
        db.rollback()
    finally:
        db.close()

def get_attention_history_counts(symbol: str) -> dict:
    from datetime import datetime, timedelta
    db = SessionLocal()
    try:
        now = datetime.now()
        dates_3 = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(5)]
        dates_5 = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        dates_10 = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(14)]
        dates_30 = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(45)]
        
        all_records = db.query(AttentionStockHistory).filter(AttentionStockHistory.symbol == symbol).all()
        dates_set = set(r.date_str for r in all_records)
        
        return {
            'count_3d': sum(1 for d in dates_3 if d in dates_set),
            'count_5d': sum(1 for d in dates_5 if d in dates_set),
            'count_10d': sum(1 for d in dates_10 if d in dates_set),
            'count_30d': sum(1 for d in dates_30 if d in dates_set)
        }
    finally:
        db.close()

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def add_tracked_stock(user_id: str, symbol: str):
    db = SessionLocal()
    try:
        symbol = symbol.upper()
        # 檢查是否已追蹤
        existing = db.query(TrackedStock).filter(TrackedStock.user_id == user_id, TrackedStock.symbol == symbol).first()
        if existing:
            return False, "已追蹤此股票"
        
        new_stock = TrackedStock(user_id=user_id, symbol=symbol)
        db.add(new_stock)
        db.commit()
        return True, "成功新增追蹤"
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()

def remove_tracked_stock(user_id: str, symbol: str):
    db = SessionLocal()
    try:
        symbol = symbol.upper()
        stock = db.query(TrackedStock).filter(TrackedStock.user_id == user_id, TrackedStock.symbol == symbol).first()
        if not stock:
            return False, "您並未追蹤此股票"
        
        db.delete(stock)
        db.commit()
        return True, "成功移除追蹤"
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()

def get_tracked_stocks(user_id: str):
    db = SessionLocal()
    try:
        stocks = db.query(TrackedStock).filter(TrackedStock.user_id == user_id).all()
        return [stock.symbol for stock in stocks]
    finally:
        db.close()

def get_all_users_and_stocks():
    db = SessionLocal()
    try:
        users = db.query(TrackedStock.user_id).distinct().all()
        result = {}
        for (user_id,) in users:
            stocks = db.query(TrackedStock.symbol).filter(TrackedStock.user_id == user_id).all()
            result[user_id] = [s for (s,) in stocks]
        return result
    finally:
        db.close()

if __name__ == "__main__":
    # 簡單測試
    print("Testing DB...")
    test_user = "U123456789"
    print(add_tracked_stock(test_user, "AAPL"))
    print(add_tracked_stock(test_user, "2330.TW"))
    print(add_tracked_stock(test_user, "AAPL")) # Should say already tracked
    print("Tracked:", get_tracked_stocks(test_user))
    print(remove_tracked_stock(test_user, "AAPL"))
    print("Tracked after remove:", get_tracked_stocks(test_user))
