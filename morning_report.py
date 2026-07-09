import argparse
import os
import sys
from datetime import datetime
import gspread
import requests
import json
from dotenv import load_dotenv
# ➕ เพิ่มการอิมพอร์ตสำหรับเรียกใช้ Gemini
from google import genai

load_dotenv()

# ... ฟังก์ชัน summarize_for_date() และ send_telegram_notification() คงเดิมไว้ ...
def summarize_for_date(rows: list, target_date: str) -> str:
    """[Pure Function] รับข้อมูลแถวทั้งหมด และวันที่ที่ต้องการ 
    ส่งกลับมาเป็นข้อความสรุปยอดขาย (Message)
    """
    total_sales = 0
    item_counts = {}

    for row in rows:
        # สมมติข้อมูลโครงสร้าง Schema: [Timestamp, Menu, Qty, Price, Total]
        # ตรวจสอบว่าในแถวนั้นมีข้อมูลครบ และเป็นของวันที่ต้องการหรือไม่
        if len(row) >= 5 and row[0].startswith(target_date):
            try:
                menu = row[1]
                qty = int(row[2])
                total = float(row[4])
                
                total_sales += total
                item_counts[menu] = item_counts.get(menu, 0) + qty
            except ValueError:
                continue # ข้ามแถวหัวตารางหรือข้อมูลที่แปลงเลขไม่ได้

    # จัดรูปแบบข้อความสรุปรายงาน
    if not item_counts:
        return f"📊 รายงานยอดขายประจำวันที่ {target_date}\n❌ ไม่มี ยอดขายในวันนี้"

    message = f"📊 รายงานยอดขายประจำวันที่ {target_date}\n"
    message += "-------------------------\n"
    for menu, qty in item_counts.items():
        message += f"- {menu}: {qty} ขวด\n"
    message += "-------------------------\n"
    message += f"💰 ยอดรวมทั้งหมด: {total_sales} บาท"
    
    return message


def send_telegram_notification(message: str) -> None:
    """ส่งรายงานเข้า Telegram Bot"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    
    response = requests.post(url, json=payload, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"Telegram API Error: {response.text}")
    
def main() -> int:
    parser = argparse.ArgumentParser(description="MilkLab Morning Report with AI")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="วันที่ต้องการสรุปยอด (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="แสดงรายงานบนจอโดยไม่ส่งเข้า Telegram")
    args = parser.parse_args()

    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    api_key = os.getenv("GOOGLE_API_KEY") # ➕ ดึงคีย์ Gemini ที่อยู่ใน .env มาใช้
    
    if not sheet_id or not api_key:
        print("[ERROR] Missing GOOGLE_SHEETS_ID or GOOGLE_API_KEY in env", file=sys.stderr)
        return 1

    try:
        # 1. ดึงข้อมูลดิบจาก Google Sheet
        cred_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        
        if cred_json:
            # 🌐 ถ้ารันบน GitHub Actions หรือระบุใน env (มีนาใช้งานเป็น String JSON)
            cred_dict = json.loads(cred_json)
            client = gspread.service_account_from_dict(cred_dict)
        else:
            # 💻 ถ้ารันบนเครื่องตัวเอง (Local) และไม่มีค่าใน env ให้ดึงจากไฟล์ตรงๆ
            if os.path.exists("credentials.json"):
                client = gspread.service_account(filename="credentials.json")
            else:
                print("[ERROR] ไม่พบข้อมูลสิทธิ์กูเกิลชีต (ไม่มีทั้งใน ENV และไฟล์ credentials.json)", file=sys.stderr)
                return 1

        sheet = client.open_by_key(sheet_id).sheet1
        all_rows = sheet.get_all_values()
        
        # 2. ให้ Python คำนวณยอดดิบออกมาก่อน (เพื่อความถูกต้องของตัวเลข)
        raw_report = summarize_for_date(all_rows, args.date)
        
        # 🛑 ถ้าวันนั้นไม่มียอดขาย ไม่จำเป็นต้องส่งให้ AI คิดต่อ
        if "❌ ไม่มี ยอดขายในวันนี้" in raw_report:
            final_message = raw_report
        else:
            # 3. 🤖 เริ่มกระบวนการส่งให้ AI สรุปและวิเคราะห์ต่อ
            print("[INFO] กำลังให้ Gemini AI สรุปรายงาน...")
            ai_client = genai.Client(api_key=api_key)
            
            prompt = f"""
            คุณเป็นผู้ช่วยผู้จัดการร้าน MilkLab ช่วยนำข้อมูลสรุปยอดขายประจำวันด้านล่างนี้ 
            มาเขียนเป็น 'รายงานสรุปยามเช้า (Morning Report)' สไตล์น่ารักเป็นกันเอง 
            โดยสรุปให้เห็นภาพรวมว่าเมนูไหนขายดี เมนูไหนควรเชียร์เพิ่ม และกล่าวทักทายทีมงานในกลุ่ม Telegram
            
            ข้อมูลยอดขายดิบ:
            {raw_report}
            """
            
            # เรียกใช้โมเดล Gemini สำเร็จรูป
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            final_message = response.text

        # 4. ตรวจสอบโหมดทดสอบ
        if args.dry_run:
            print("⚠️ [DRY RUN MODE] รายงานจาก AI นี้จะไม่ถูกส่งเข้า Telegram:")
            print(final_message)
            return 0
            
        # 5. ส่งข้อความสุดท้ายที่ผ่านการเรียบเรียงจาก AI เข้า Telegram
        send_telegram_notification(final_message)
        print(f"[OK] ส่งรายงานสรุปผ่าน AI ประจำวันที่ {args.date} เข้า Telegram เรียบร้อยแล้ว!")
        return 0

    except Exception as exc:
        print(f"[ERROR] เกิดข้อผิดพลาดในระบบรายงาน AI: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())