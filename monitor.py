import os
import json
import time
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
import yfinance as yf
from datetime import datetime

EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_TO")
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465

SYMBOLS = {
    "WTI原油": "CL=F",
    "Brent原油": "BZ=F",
    "十年期美债收益率": "^TNX"
}

THRESHOLD = 0.01          # 变动阈值：1%
CHECK_INTERVAL = 30       # 采样频率：每 30 秒检测一次
RUN_DURATION = 840        # 每次任务持续运行 14 分钟（留 1 分钟缓冲给接力任务）
CACHE_FILE = "market_baseline.json"

def send_email(subject, html_content):
    msg = MIMEText(html_content, 'html', 'utf-8')
    msg['From'] = formataddr((str(Header("行情监控小助手", 'utf-8')), EMAIL_USER))
    msg['To'] = formataddr((str(Header("接收人", 'utf-8')), EMAIL_TO))
    msg['Subject'] = Header(subject, 'utf-8')

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        server.quit()
        print("✅ 告警邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def load_baselines():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_baselines(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fetch_latest_prices():
    prices = {}
    for name, ticker_code in SYMBOLS.items():
        try:
            ticker = yf.Ticker(ticker_code)
            df = ticker.history(period="1d", interval="1m")
            if not df.empty:
                prices[name] = round(float(df["Close"].iloc[-1]), 3)
            else:
                info_price = ticker.fast_info.get("last_price")
                if info_price:
                    prices[name] = round(float(info_price), 3)
        except Exception as e:
            print(f"[{name}] 获取价格异常: {e}")
    return prices

def check_market():
    baselines = load_baselines()
    current_prices = fetch_latest_prices()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alerts = []

    for name, current in current_prices.items():
        base = baselines.get(name)
        if base is not None and base > 0:
            change_ratio = (current - base) / base
            change_pct = change_ratio * 100

            if abs(change_ratio) >= THRESHOLD:
                direction = "📈 快速拉升" if change_ratio > 0 else "📉 快速跳水"
                color = "#d93025" if change_ratio > 0 else "#188038"
                sign = "+" if change_ratio > 0 else ""
                unit = "%" if "收益率" in name else " USD"

                alert_html = f"""
                <div style="border-left: 4px solid {color}; padding-left: 10px; margin-bottom: 15px;">
                    <h3 style="margin: 0; color: #202124;">{name} {direction}</h3>
                    <p style="margin: 4px 0; color: #5f6368;">最新现价：<b style="color: #202124;">{current}{unit}</b></p>
                    <p style="margin: 4px 0; color: #5f6368;">前次基准：{base}{unit}</p>
                    <p style="margin: 4px 0; color: #5f6368;">波动幅度：<b style="color: {color};">{sign}{change_pct:.2f}%</b></p>
                </div>
                """
                alerts.append(alert_html)
                baselines[name] = current
        else:
            baselines[name] = current
            print(f"[{now_str}] 记录基准 -> {name}: {current}")

    save_baselines(baselines)

    if alerts:
        subject = "⚠️ 市场突发异动报警 (>1%)"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h2 style="color: #d93025; margin-top: 0;">市场突发波动通知</h2>
            {''.join(alerts)}
            <hr style="border: none; border-top: 1px solid #eee; margin-top: 20px;" />
            <small style="color: #888;">检测时间：{now_str}</small>
        </div>
        """
        send_email(subject, html_body)
    else:
        print(f"[{now_str}] 30秒周期检测正常，无单次异动超 1%。")

def main():
    print(f"🚀 启动 30 秒高频监控，当前任务将持续轮询 {RUN_DURATION // 60} 分钟...")
    start_time = time.time()
    
    while time.time() - start_time < RUN_DURATION:
        try:
            check_market()
        except Exception as e:
            print(f"检测异常: {e}")
        time.sleep(CHECK_INTERVAL)

    print("🏁 当前批次检测结束，退出以便保存最新基准并等待下一批接力。")

if __name__ == "__main__":
    main()
