"""SolarPlus Agent Tools (S2) — เดิมเป็น tools ของ MilkLab

pivot mapping:
  log_sale     -> log_lead        (บันทึกลีดลูกค้า ไม่ใช่ยอดขายน้ำ)
  query_sales  -> query_leads     (สรุปลีดรายวัน)
  send_alert   -> send_alert      (เหมือนเดิม ยังต้อง confirm=True ก่อนส่ง)
  (ใหม่)       -> estimate_solar  (คำนวณขนาด/ราคา/คืนทุน ด้วย Python ล้วน)

ทุก tool คืน dict ที่มี key 'ok' เสมอ เพื่อให้ harness แยก success/error ได้แบบเดียวกัน
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import lead_logger
import lead_report
import solar_calc

# ค่าไฟที่รับได้ ใช้ validate ก่อนเรียก solar_calc อีกชั้น
MAX_CONTACT_LEN = 100
MAX_NAME_LEN = 100


def _validate_lead(name, contact, monthly_bill):
    if not name or not str(name).strip():
        return 'name must not be empty'
    if len(str(name)) > MAX_NAME_LEN:
        return 'name too long'
    if not contact or not str(contact).strip():
        return 'contact must not be empty (ต้องมีเบอร์โทรหรือ LINE ID ไว้ติดต่อกลับ)'
    if len(str(contact)) > MAX_CONTACT_LEN:
        return 'contact too long'
    if monthly_bill <= 0:
        return 'monthly_bill > 0'
    if monthly_bill > solar_calc.MAX_BILL:
        return f'monthly_bill too large (> {solar_calc.MAX_BILL:,})'
    return None


def log_lead(name, contact, monthly_bill):
    """บันทึกลีดลูกค้าลง Sheet + แจ้งเตือนเจ้าของร้านทาง Telegram"""
    err = _validate_lead(name, contact, monthly_bill)
    if err:
        return {'ok': False, 'tool': 'log_lead', 'error': err}

    try:
        return lead_logger.append_lead(name, contact, monthly_bill)
    except RuntimeError as e:
        return {'ok': False, 'tool': 'log_lead', 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'tool': 'log_lead', 'error': f'unexpected error: {e}'}


def estimate_solar(monthly_bill):
    """ประเมินขนาดระบบ/ราคา/คืนทุน — read-only ไม่มี side effect

    tool นี้คือหัวใจของ pivot: LLM แค่ดึงตัวเลขค่าไฟจากประโยคไทย
    ส่วนการคำนวณทั้งหมดเป็น Python เพื่อให้ผลลัพธ์เหมือนเดิมทุกครั้ง ตรวจสอบย้อนหลังได้
    """
    try:
        result = solar_calc.estimate(monthly_bill)
    except solar_calc.EstimateError as e:
        return {'ok': False, 'tool': 'estimate_solar', 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'tool': 'estimate_solar', 'error': f'unexpected error: {e}'}

    return {
        'ok': True,
        'tool': 'estimate_solar',
        'summary': solar_calc.format_th(result),
        **result,
    }


def _validate_query_date(date):
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except (TypeError, ValueError):
        return 'date must be YYYY-MM-DD'
    return None


def query_leads(date=None):
    """สรุปลีดของวันที่ระบุ ถ้าไม่ระบุ default = เมื่อวาน

    ดึง rows ดิบจาก Sheet ผ่าน lead_logger.get_all_rows()
    แล้วส่งให้ lead_report.summarize_for_date(rows, date) สรุปข้อความ
    """
    if date is None:
        date = (datetime.now(ZoneInfo("Asia/Bangkok")) - timedelta(days=1)).strftime('%Y-%m-%d')

    err = _validate_query_date(date)
    if err:
        return {'ok': False, 'tool': 'query_leads', 'error': err}

    try:
        rows = lead_logger.get_all_rows()
        summary_text = lead_report.summarize_for_date(rows, date)
    except RuntimeError as e:
        return {'ok': False, 'tool': 'query_leads', 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'tool': 'query_leads', 'error': f'unexpected error: {e}'}

    return {'ok': True, 'tool': 'query_leads', 'date': date, 'summary': summary_text}


def _validate_alert(message, confirm):
    if not message or not str(message).strip():
        return 'message must not be empty'
    if not confirm:
        return 'confirm must be true ก่อนส่งแจ้งเตือนจริง (side effect ต้องยืนยันก่อน)'
    return None


def send_alert(message, confirm=False):
    """ส่ง message แจ้งเตือนเจ้าของร้านผ่าน Telegram

    ต้อง confirm=True ก่อนถึงจะยอมส่งจริง กันโมเดลยิง notification โดยไม่ตั้งใจ
    send_telegram_notification ไม่ return อะไร (None) — ถ้าไม่ raise แปลว่าส่งสำเร็จ
    """
    err = _validate_alert(message, confirm)
    if err:
        return {'ok': False, 'tool': 'send_alert', 'error': err}

    try:
        lead_report.send_telegram_notification(message)
    except RuntimeError as e:
        return {'ok': False, 'tool': 'send_alert', 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'tool': 'send_alert', 'error': f'telegram error: {e}'}

    return {'ok': True, 'tool': 'send_alert', 'message': message, 'notified_via': 'telegram'}


TOOL_REGISTRY = {
    'log_lead': {
        'fn': log_lead,
        'args': ('name', 'contact', 'monthly_bill'),
        'coerce': {'name': str, 'contact': str, 'monthly_bill': float},
    },
    'estimate_solar': {
        'fn': estimate_solar,
        'args': ('monthly_bill',),
        'coerce': {'monthly_bill': float},
    },
    'query_leads': {
        'fn': query_leads,
        'args': ('date',),  # agent_harness.dispatch_tool แปลง period -> date จริงมาให้แล้ว
        'coerce': {'date': str},
    },
    'send_alert': {
        'fn': send_alert,
        'args': ('message', 'confirm'),
        'coerce': {'message': str, 'confirm': bool},
    },
}