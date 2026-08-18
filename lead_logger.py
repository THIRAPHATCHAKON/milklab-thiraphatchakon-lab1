"""SolarPlus Lead Logger (S2) — เดิมคือ sales_logger.py

Usage:
    python lead_logger.py --name "คุณสมชาย" --contact "081-234-5678" --bill 3000

อ่าน GOOGLE_SHEETS_CREDENTIALS / GOOGLE_SHEETS_ID / TELEGRAM_BOT_TOKEN จาก env
append row [timestamp, name, contact, monthly_bill, kw, price, payback_years, note] ลง Google Sheet
แล้วแจ้งเตือนเจ้าของร้านผ่าน Telegram ว่ามีลีดใหม่

pivot: เดิมบันทึก "ยอดขายน้ำ" -> ตอนนี้บันทึก "ลีดลูกค้า + ผลประเมินเบื้องต้น"
เพราะ pain point คือเจ้าของไม่มีเวลารับสาย ต้องได้ข้อมูลลูกค้าไว้ก่อนแล้วค่อยโทรกลับ
"""

import argparse
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
import requests
from dotenv import load_dotenv

import solar_calc

load_dotenv()

# หัวตารางของ Sheet — ต้องตรงกับลำดับที่ append_to_sheet เขียนลงไป
SHEET_HEADER = [
    "timestamp",
    "name",
    "contact",
    "monthly_bill",
    "recommended_kw",
    "price",
    "payback_years",
    "note",
]


def _open_sheet():
    """เปิด worksheet เดียวกันทุกฟังก์ชัน — รวมโค้ด auth ไว้ที่เดียว

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
        return client.open_by_key(sheet_id).sheet1
    except json.JSONDecodeError as e:
        raise RuntimeError(f"GOOGLE_SHEETS_CREDENTIALS is not valid JSON: {e}")
    except Exception as e:
        raise RuntimeError(f"Google Sheet error: {e}")


def append_to_sheet(name: str, contact: str, monthly_bill: float, note: str = "") -> dict:
    """บันทึกลีด 1 รายลง Sheet พร้อมผลประเมินที่คำนวณด้วย solar_calc

    ประเมินตอน "บันทึก" ไม่ใช่ตอนอ่านทีหลัง เพื่อให้เจ้าของเห็นตัวเลขทันทีใน Sheet
    ถ้าค่าไฟไม่ผ่าน validation จะยังบันทึกลีดไว้ แต่เว้นช่องผลประเมินว่าง
    (ลีดสำคัญกว่าตัวเลข — ห้ามทิ้งลูกค้าเพราะกรอกค่าไฟเพี้ยน)
    """
    sheet = _open_sheet()

    timestamp = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S")

    try:
        est = solar_calc.estimate(monthly_bill)
        kw, price, payback = est["recommended_kw"], est["price"], est["payback_years"]
    except solar_calc.EstimateError as e:
        est = None
        kw, price, payback = "", "", ""
        note = f"{note} | ประเมินไม่ได้: {e}".strip(" |")

    row_data = [timestamp, name, contact, monthly_bill, kw, price, payback, note]

    try:
        sheet.append_row(row_data)
    except Exception as e:
        raise RuntimeError(f"Google Sheet append error: {e}")

    return {
        "timestamp": timestamp,
        "name": name,
        "contact": contact,
        "monthly_bill": monthly_bill,
        "recommended_kw": kw,
        "price": price,
        "payback_years": payback,
        "note": note,
        "estimate": est,
    }


def get_all_rows() -> list:
    """คืน rows ดิบทั้งหมดจาก Sheet
    ใช้โดย agent_tools.query_leads -> lead_report.summarize_for_date(rows, date)
    """
    sheet = _open_sheet()
    try:
        return sheet.get_all_values()
    except Exception as e:
        raise RuntimeError(f"Google Sheet read error: {e}")


def send_notification(message: str) -> str:
    """ส่ง message ไปยัง Telegram bot ของเจ้าของร้าน

    Returns: provider name ("telegram")
    Raises RuntimeError ถ้าไม่มี credentials หรือยิงไม่สำเร็จ
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in environment")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"Telegram API status {response.status_code}: {response.text}")
        return "telegram"
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Telegram notification failed: {e}")


def append_lead(name: str, contact: str, monthly_bill: float, note: str = "") -> dict:
    """Wrapper ที่ agent_tools เรียกใช้ — single entry point
    รวม append_to_sheet + send_notification ไว้ที่เดียว

    ถ้าบันทึก Sheet สำเร็จแต่แจ้งเตือนล้มเหลว ยังถือว่า ok=True
    """
    row = append_to_sheet(name, contact, monthly_bill, note)

    summary_line = (
        f"{row['recommended_kw']} kW / {row['price']:,} บาท / คืนทุน {row['payback_years']} ปี"
        if row["estimate"]
        else "ยังประเมินไม่ได้"
    )
    message = (
        "ลีดใหม่ SolarPlus\n"
        f"ชื่อ: {name}\n"
        f"ติดต่อ: {contact}\n"
        f"ค่าไฟ: {monthly_bill:,.0f} บาท/เดือน\n"
        f"ประเมินเบื้องต้น: {summary_line}"
    )

    try:
        provider = send_notification(message)
    except RuntimeError:
        provider = None

    return {
        "ok": True,
        "timestamp": row["timestamp"],
        "name": row["name"],
        "contact": row["contact"],
        "monthly_bill": row["monthly_bill"],
        "recommended_kw": row["recommended_kw"],
        "price": row["price"],
        "payback_years": row["payback_years"],
        "notified_via": provider,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SolarPlus Lead Logger")
    parser.add_argument("--name", required=True, help="ชื่อลูกค้า")
    parser.add_argument("--contact", required=True, help="เบอร์โทร / LINE ID")
    parser.add_argument("--bill", type=float, required=True, help="ค่าไฟเฉลี่ยต่อเดือน (บาท)")
    parser.add_argument("--note", default="", help="หมายเหตุเพิ่มเติม")
    args = parser.parse_args()

    try:
        row = append_to_sheet(args.name, args.contact, args.bill, args.note)
    except Exception as exc:
        print(f"[ERROR] บันทึก Sheet ล้มเหลว: {exc}", file=sys.stderr)
        print(
            "[HINT] ตรวจ GOOGLE_SHEETS_CREDENTIALS และ share Sheet กับ service account email",
            file=sys.stderr,
        )
        return 1

    if row["estimate"]:
        print(solar_calc.format_th(row["estimate"]))

    try:
        provider = send_notification(
            f"ลีดใหม่: {args.name} ({args.contact}) ค่าไฟ {args.bill:,.0f} บาท/เดือน"
        )
    except Exception as exc:
        print(f"[WARN] บันทึก Sheet สำเร็จแต่ส่งแจ้งเตือนล้มเหลว: {exc}", file=sys.stderr)
        return 0

    print(f"[OK] บันทึกลีดและแจ้งเตือนผ่าน {provider} เรียบร้อย")
    return 0


if __name__ == "__main__":
    sys.exit(main())
