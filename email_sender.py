import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

def send_email(subject: str, content: str):
    """
    發送電子郵件的模組
    使用 Gmail SMTP 伺服器
    """
    sender = os.environ.get("GMAIL_SENDER_ACCOUNT", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient = os.environ.get("GMAIL_RECIPIENT_ACCOUNT", "")

    if not sender or not password or not recipient:
        print("Email not sent: Gmail credentials or recipient not configured in .env")
        return False

    msg = MIMEMultipart()
    msg['From'] = f"股市監控機器人 <{sender}>"
    msg['To'] = recipient
    msg['Subject'] = subject

    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        # 連線至 Gmail SMTP 伺服器
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        # 登入
        server.login(sender, password)
        # 寄信
        server.send_message(msg)
        server.quit()
        print(f"Successfully sent email: '{subject}' to {recipient}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
