"""SolarPlus Lead Report (S2) — เดิมคือ morning_report.py

หน้าที่เดิม: สรุปยอดขายรายวัน -> ตอนนี้: สรุป "ลีดลูกค้ารายวัน" ให้เจ้าของร้าน
รักษาชื่อฟังก์ชันเดิมไว้ (summarize_for_date / send_telegram_notification)
เพื่อให้ agent_tools.py เรียกใช้แบบเดิมได้ ไม่ต้องแก้ interface

ลำดับคอลัมน์ต้องตรงกับ lead_logger.SHEET_HEADER:
  0 timestamp | 1 name | 2 contact | 3 monthly_bill | 4 kw | 5 price | 6 payback | 7 note
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import lead_logger

COL_TIMESTAMP = 0
COL_NAME = 1
COL_CONTACT = 2
COL_BILL = 3
COL_KW = 4
COL_PRICE = 5
COL_PAYBACK = 6


def _to_float(value) -> float:
    """แปลงค่าจาก Sheet (ที่มาเป็น string เสมอ) เป็น float แบบไม่ระเบิด

    Sheet อาจใส่ comma มาให้ เช่น "165,000" -> ต้องตัดออกก่อน
    ค่าว่าง/ค่าเพี้ยน คืน 0.0 แล้วให้ผู้เรียกตัดสินใจเอง
    """
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def summarize_for_date(rows: list, date: str) -> str:
    """สรุปลีดของวันที่ระบุ (YYYY-MM-DD) เป็นข้อความไทย 1 ก้อน

    rows = ผลจาก lead_logger.get_all_rows() (รวมแถว header)
    กรองด้วย timestamp.startswith(date) — header จึงถูกตัดออกเองโดยอัตโนมัติ
    """
    matched = [
        r for r in rows
        if len(r) > COL_TIMESTAMP and str(r[COL_TIMESTAMP]).startswith(date)
    ]

    if not matched:
        return f"วันที่ {date} ยังไม่มีลีดลูกค้าเข้ามา"

    total_bill = sum(_to_float(r[COL_BILL]) for r in matched if len(r) > COL_BILL)
    pipeline_value = sum(_to_float(r[COL_PRICE]) for r in matched if len(r) > COL_PRICE)

    paybacks = [
        _to_float(r[COL_PAYBACK])
        for r in matched
        if len(r) > COL_PAYBACK and _to_float(r[COL_PAYBACK]) > 0
    ]
    avg_payback = sum(paybacks) / len(paybacks) if paybacks else 0.0

    lines = [
        f"สรุปลีดวันที่ {date}",
        f"จำนวนลีด: {len(matched)} ราย",
        f"ค่าไฟรวมของลีดทั้งหมด: {total_bill:,.0f} บาท/เดือน",
        f"มูลค่างานที่ประเมินได้รวม: {pipeline_value:,.0f} บาท",
    ]
    if avg_payback:
        lines.append(f"ระยะคืนทุนเฉลี่ยของลีดกลุ่มนี้: {avg_payback:.1f} ปี")

    lines.append("รายชื่อ:")
    for r in matched:
        name = r[COL_NAME] if len(r) > COL_NAME else "-"
        contact = r[COL_CONTACT] if len(r) > COL_CONTACT else "-"
        kw = r[COL_KW] if len(r) > COL_KW and r[COL_KW] else "-"
        bill = _to_float(r[COL_BILL]) if len(r) > COL_BILL else 0
        lines.append(f"  - {name} ({contact}) ค่าไฟ {bill:,.0f} บาท -> แนะนำ {kw} kW")

    return "\n".join(lines)


def send_telegram_notification(message: str) -> None:
    """ส่งข้อความไป Telegram — delegate ให้ lead_logger เพื่อไม่ให้มีโค้ดยิง API 2 ที่

    ไม่ return อะไร ถ้าไม่ raise แปลว่าส่งสำเร็จ (agent_tools พึ่ง contract นี้)
    """
    lead_logger.send_notification(message)


def send_daily_report(date: str | None = None) -> str:
    """ดึงลีดของวันที่ระบุ (default = เมื่อวาน) แล้วส่งสรุปเข้า Telegram เจ้าของร้าน

    ใช้กับ cron / GitHub Actions ตอนเช้าได้เลย
    """
    if date is None:
        date = (datetime.now(ZoneInfo("Asia/Bangkok")) - timedelta(days=1)).strftime("%Y-%m-%d")

    rows = lead_logger.get_all_rows()
    summary = summarize_for_date(rows, date)
    send_telegram_notification(summary)
    return summary


if __name__ == "__main__":
    print(send_daily_report())