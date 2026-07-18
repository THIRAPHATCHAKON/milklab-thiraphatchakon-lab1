"""MilkLab Sales Logger (S2).

Usage:
    python sales_logger.py --menu "นมหมีฮอกไกโด" --qty 2 --price 65

Reads GOOGLE_SHEETS_CREDENTIALS and TELEGRAM_BOT_TOKEN (or LINE_CHANNEL_TOKEN) from env.
Appends row [timestamp, menu, qty, price, total] to a Google Sheet,
then sends a notification via Telegram or LINE bot.

นักศึกษาต้องเติม TODO ใน 4 จุดด้านล่างใน Session 2 Lab 1.3
"""

import argparse
import os
import sys
from datetime import datetime
import gspread
import json
import requests
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

load_dotenv()


def append_to_sheet(menu: str, qty: int, price: float) -> dict:
    """TODO 1: ใช้ gspread เปิด Sheet ของตัวเอง แล้ว append_row ด้วย [timestamp, menu, qty, price, total]

    Returns dict {timestamp, menu, qty, price, total} ที่ append แล้ว
    Raises RuntimeError ถ้า credentials ไม่มี หรือ Sheet ไม่ accessible
    """
    cred_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    sheet_id = os.getenv("GOOGLE_SHEETS_ID")

    if not cred_json:
        raise RuntimeError("Missing GOOGLE_SHEETS_CREDENTIALS in environment")
    if not sheet_id:
        raise RuntimeError("Missing GOOGLE_SHEETS_ID in environment")

    try:
        # อ่านสิทธิ์จาก JSON string ใน .env โดยตรง (ไม่ต้องมีไฟล์ credentials.json แยก)
        cred_dict = json.loads(cred_json)
        client = gspread.service_account_from_dict(cred_dict)

        # เปิดหน้า Sheet ด้วย ID
        sheet = client.open_by_key(sheet_id).sheet1

        # เตรียมข้อมูลเพื่อบันทึก
        timestamp = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S")
        total = qty * price
        row_data = [timestamp, menu, qty, price, total]

        # บันทึกข้อมูลเพิ่มแถวใหม่
        sheet.append_row(row_data)

        return {
            "timestamp": timestamp,
            "menu": menu,
            "qty": qty,
            "price": price,
            "total": total,
        }

    except json.JSONDecodeError as e:
        raise RuntimeError(f"GOOGLE_SHEETS_CREDENTIALS is not valid JSON: {e}")
    except Exception as e:
        raise RuntimeError(f"Google Sheet error: {e}")


def get_all_rows() -> list:
    """เปิด Sheet เดียวกับที่ append_to_sheet ใช้ แล้วคืน rows ดิบทั้งหมด
    ใช้โดย agent_tools.query_sales -> morning_report.summarize_for_date(rows, date)

    Raises RuntimeError ถ้า credentials ไม่มี หรือ Sheet ไม่ accessible
    """
    cred_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    sheet_id = os.getenv("GOOGLE_SHEETS_ID")

    if not cred_json:
        raise RuntimeError("Missing GOOGLE_SHEETS_CREDENTIALS in environment")
    if not sheet_id:
        raise RuntimeError("Missing GOOGLE_SHEETS_ID in environment")

    try:
        cred_dict = json.loads(cred_json)
        client = gspread.service_account_from_dict(cred_dict)
        sheet = client.open_by_key(sheet_id).sheet1
        return sheet.get_all_values()
    except json.JSONDecodeError as e:
        raise RuntimeError(f"GOOGLE_SHEETS_CREDENTIALS is not valid JSON: {e}")
    except Exception as e:
        raise RuntimeError(f"Google Sheet error: {e}")


def send_notification(message: str) -> str:
    """TODO 2: ส่ง message ไปยัง Telegram bot (ใช้ TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)
    หรือ LINE bot (ใช้ LINE_CHANNEL_TOKEN) เลือกตัวใดตัวหนึ่ง

    Returns: provider name ที่ใช้ ("telegram" หรือ "line")
    Raises RuntimeError ถ้า no credentials
    """
    # 1. ดึงค่า Token และ Chat ID จากไฟล์ .env มาใช้งาน
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    # ดัก Error: ถ้าใน .env ไม่มีค่าโทเค็นหรือไอดีแชท ให้หยุดทำงานทันที
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in environment")

    # 2. เตรียม URL สำหรับคุยกับ Telegram API (สังเกตคำว่า bot ต้องติดกับรหัส token)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # 3. จัดกลุ่มข้อมูล (Payload) ที่จะส่งไปในรูปแบบ JSON ตามข้อกำหนดของ Telegram
    payload = {
        "chat_id": chat_id,
        "text": message,
    }

    try:
        # 4. ใช้ requests ยิง POST ข้อมูลไปที่ Telegram (ใส่ timeout กันโค้ดค้างถ้าเน็ตหลุด)
        response = requests.post(url, json=payload, timeout=10)
        # 5. เช็กว่า Telegram ตอบกลับมาสำเร็จไหม (ถ้าสถานะไม่ใช่ 200 แปลว่าพัง เช่น หาห้องแชทไม่เจอ)
        if response.status_code != 200:
            raise RuntimeError(f"Telegram API status {response.status_code}: {response.text}")
        # 6. ส่งชื่อผู้ให้บริการกลับไปตามที่โจทย์ระบุตัวตน ("telegram")
        return "telegram"
    except RuntimeError:
        raise
    except Exception as e:
        # ดักจับ Error ในกรณีเกิดปัญหาด้านเครือข่าย หรือเซิร์ฟเวอร์ Telegram ปฏิเสธการเชื่อมต่อ
        raise RuntimeError(f"Telegram notification failed: {e}")


def append_sale(menu: str, quantity: int, price: float) -> dict:
    """Wrapper ที่ agent_tools.py (S3) เรียกใช้โดยตรง — single entry point
    รวม append_to_sheet + send_notification ไว้ในที่เดียว ("เรียกของ S2 ตรงๆ")

    ถ้าบันทึก Sheet สำเร็จแต่ notification ล้มเหลว ยังถือว่า ok=True
    (ข้อมูลเข้า Sheet แล้ว แค่แจ้งเตือนไม่ได้)
    """
    row = append_to_sheet(menu, quantity, price)

    try:
        provider = send_notification(
            f"บันทึกขาย {menu} x{quantity} = {row['total']} บาท"
        )
    except RuntimeError:
        provider = None

    return {
        "ok": True,
        "timestamp": row["timestamp"],
        "menu": row["menu"],
        "quantity": row["qty"],
        "price": row["price"],
        "total": row["total"],
        "notified_via": provider,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MilkLab Sales Logger")
    parser.add_argument("--menu", required=True, help="ชื่อเมนู")
    parser.add_argument("--qty", type=int, required=True, help="จำนวนขวด")
    parser.add_argument("--price", type=float, required=True, help="ราคาต่อขวด")
    args = parser.parse_args()

    try:
        # TODO 3: เรียก append_to_sheet แล้ว extract total
        row = append_to_sheet(args.menu, args.qty, args.price)
        total = row["total"]
    except Exception as exc:
        print(f"[ERROR] บันทึก Sheet ล้มเหลว: {exc}", file=sys.stderr)
        print("[HINT] ตรวจ GOOGLE_SHEETS_CREDENTIALS และ share Sheet กับ service account email", file=sys.stderr)
        return 1

    try:
        # TODO 4: เรียก send_notification ด้วย message ที่บอกยอดที่บันทึก
        provider = send_notification(f"บันทึก {args.menu} x{args.qty} = {total} บาท")
    except Exception as exc:
        print(f"[WARN] บันทึก Sheet สำเร็จแต่ส่งแจ้งเตือนล้มเหลว: {exc}", file=sys.stderr)
        return 0

    print(f"[OK] บันทึกและแจ้งเตือนผ่าน {provider} เรียบร้อย ยอด {total} บาท")
    return 0


if __name__ == "__main__":
    sys.exit(main())