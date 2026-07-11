# agent_tools.py
from datetime import datetime
import sales_logger, morning_report

def _validate_sale(menu, qty, price):
    if qty <= 0:        return 'qty > 0'
    if price < 0:       return 'price >= 0'
    if qty > 500:        return 'qty too large'
    return None

def log_sale(menu, quantity, price):
    err = _validate_sale(menu, quantity, price)
    if err: return {'ok': False, 'tool':'log_sale', 'error': err}
    return sales_logger.append_sale(menu, quantity, price)

TOOL_REGISTRY = {
    'log_sale': {'fn': log_sale,
                 'args': ('menu','quantity','price'),
                 'coerce': {'menu':str,'quantity':int,'price':float}}
}