# # 

# # agent_tools.py
# from datetime import datetime, timedelta

# import sales_logger
# import morning_report


# def _validate_sale(menu, qty, price):
#     if not menu or not str(menu).strip():
#         return 'menu must not be empty'
#     if qty <= 0:
#         return 'qty > 0'
#     if price < 0:
#         return 'price >= 0'
#     if qty > 500:
#         return 'qty too large'
#     return None


# def log_sale(menu, quantity, price):
#     err = _validate_sale(menu, quantity, price)
#     if err:
#         return {'ok': False, 'tool': 'log_sale', 'error': err}
#     return sales_logger.append_sale(menu, quantity, price)


# def _validate_query_date(date):
#     try:
#         datetime.strptime(date, '%Y-%m-%d')
#     except (TypeError, ValueError):
#         return 'date must be YYYY-MM-DD'
#     return None


# def query_sales(date=None):
#     """ดูสรุปยอดขายของวันที่ระบุ ถ้าไม่ระบุ default = เมื่อวาน (ตรงกับ get_yesterday_summary())"""
#     if date is None:
#         date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

#     err = _validate_query_date(date)
#     if err:
#         return {'ok': False, 'tool': 'query_sales', 'error': err}

#     try:
#         summary = morning_report.get_summary(date)
#     except Exception as e:
#         return {'ok': False, 'tool': 'query_sales', 'error': f'morning_report error: {e}'}

#     if isinstance(summary, dict):
#         summary.setdefault('ok', True)
#         summary.setdefault('tool', 'query_sales')
#         summary.setdefault('date', date)
#         return summary
#     return {'ok': True, 'tool': 'query_sales', 'date': date, 'summary': summary}


# def _validate_alert(message, confirm):
#     if not message or not str(message).strip():
#         return 'message must not be empty'
#     if not confirm:
#         return 'confirm must be true ก่อนส่งแจ้งเตือนจริง (side effect ต้องยืนยันก่อน)'
#     return None


# def send_alert(message, confirm=False):
#     """ส่ง message แจ้งเตือนผ่าน Bot (ใช้ morning_report ประกอบ/ส่งรายงาน)

#     ต้อง confirm=True ก่อนถึงจะยอมส่งจริง กันโมเดลยิง notification โดยไม่ตั้งใจ
#     """
#     err = _validate_alert(message, confirm)
#     if err:
#         return {'ok': False, 'tool': 'send_alert', 'error': err}

#     try:
#         provider = morning_report.send_report(message)
#     except AttributeError:
#         # เผื่อ morning_report ยังไม่มี send_report ให้ fallback ไป sales_logger.send_notification
#         provider = sales_logger.send_notification(message)
#     except Exception as e:
#         return {'ok': False, 'tool': 'send_alert', 'error': f'morning_report error: {e}'}

#     return {'ok': True, 'tool': 'send_alert', 'message': message, 'notified_via': provider}


# TOOL_REGISTRY = {
#     'log_sale': {
#         'fn': log_sale,
#         'args': ('menu', 'quantity', 'price'),
#         'coerce': {'menu': str, 'quantity': int, 'price': float},
#     },
#     'query_sales': {
#         'fn': query_sales,
#         'args': (),  # get_yesterday_summary() ไม่รับ argument ตาม SYSTEM_INSTRUCTION
#         'coerce': {},
#     },
#     'send_alert': {
#         'fn': send_alert,
#         'args': ('message', 'confirm'),
#         'coerce': {'message': str, 'confirm': bool},
#     },
# }

# agent_tools.py
# agent_tools.py
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import sales_logger
import morning_report


def _validate_sale(menu, qty, price):
    if not menu or not str(menu).strip():
        return 'menu must not be empty'
    if qty <= 0:
        return 'qty > 0'
    if price < 0:
        return 'price >= 0'
    if qty > 500:
        return 'qty too large'
    return None


def log_sale(menu, quantity, price):
    err = _validate_sale(menu, quantity, price)
    if err:
        return {'ok': False, 'tool': 'log_sale', 'error': err}
    return sales_logger.append_sale(menu, quantity, price)


def _validate_query_date(date):
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except (TypeError, ValueError):
        return 'date must be YYYY-MM-DD'
    return None


def query_sales(date=None):
    """ดูสรุปยอดขายของวันที่ระบุ ถ้าไม่ระบุ default = เมื่อวาน (ตรงกับ get_yesterday_summary())

    ดึง rows ดิบจาก Sheet ผ่าน sales_logger.get_all_rows() ก่อน
    แล้วส่งให้ morning_report.summarize_for_date(rows, date) สรุปข้อความ
    """
    if date is None:
        date = (datetime.now(ZoneInfo("Asia/Bangkok")) - timedelta(days=1)).strftime('%Y-%m-%d')

    err = _validate_query_date(date)
    if err:
        return {'ok': False, 'tool': 'query_sales', 'error': err}

    try:
        rows = sales_logger.get_all_rows()
        summary_text = morning_report.summarize_for_date(rows, date)
    except RuntimeError as e:
        return {'ok': False, 'tool': 'query_sales', 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'tool': 'query_sales', 'error': f'unexpected error: {e}'}

    return {'ok': True, 'tool': 'query_sales', 'date': date, 'summary': summary_text}


def _validate_alert(message, confirm):
    if not message or not str(message).strip():
        return 'message must not be empty'
    if not confirm:
        return 'confirm must be true ก่อนส่งแจ้งเตือนจริง (side effect ต้องยืนยันก่อน)'
    return None


def send_alert(message, confirm=False):
    """ส่ง message แจ้งเตือนผ่าน Telegram (morning_report.send_telegram_notification)

    ต้อง confirm=True ก่อนถึงจะยอมส่งจริง กันโมเดลยิง notification โดยไม่ตั้งใจ
    send_telegram_notification ไม่ return อะไร (None) — ถ้าไม่ raise แปลว่าส่งสำเร็จ
    """
    err = _validate_alert(message, confirm)
    if err:
        return {'ok': False, 'tool': 'send_alert', 'error': err}

    try:
        morning_report.send_telegram_notification(message)
    except RuntimeError as e:
        return {'ok': False, 'tool': 'send_alert', 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'tool': 'send_alert', 'error': f'telegram error: {e}'}

    return {'ok': True, 'tool': 'send_alert', 'message': message, 'notified_via': 'telegram'}


TOOL_REGISTRY = {
    'log_sale': {
        'fn': log_sale,
        'args': ('menu', 'quantity', 'price'),
        'coerce': {'menu': str, 'quantity': int, 'price': float},
    },
    'query_sales': {
        'fn': query_sales,
        'args': ('date',),  # agent_harness.dispatch_tool แปลง period -> date จริงมาให้แล้ว
        'coerce': {'date': str},
    },
    'send_alert': {
        'fn': send_alert,
        'args': ('message', 'confirm'),
        'coerce': {'message': str, 'confirm': bool},
    },
}