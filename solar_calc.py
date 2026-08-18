"""SolarPlus Estimator — คำนวณขนาดระบบ / ราคา / คืนทุน

หัวใจของ pivot: ตัวเลขทั้งหมดคำนวณด้วย Python ไม่ให้ LLM เดา
LLM มีหน้าที่แค่ "ดึงค่าไฟต่อเดือน" ออกจากประโยคภาษาไทย แล้วส่งมาให้ฟังก์ชันนี้

ใช้ร่วมกัน 2 ที่:
  - agent_tools.estimate_solar()  (S2 agent)
  - app.py sidebar + context injection (S3 RAG chatbot)

สมมติฐานทุกตัวรวมไว้ข้างล่างที่เดียว แก้ที่นี่ที่เดียวแล้วมีผลทั้งระบบ
ต้องแก้ให้ตรงกับราคาจริงของร้านก่อน deploy
"""

# ค่าไฟเฉลี่ยต่อหน่วย (บาท/kWh) — รวม Ft และภาษีแล้วโดยประมาณ
ELECTRICITY_RATE = 4.5

# ระบบ 1 kW ผลิตไฟได้กี่หน่วยต่อเดือน (ไทยประมาณ 4 หน่วย/วัน)
MONTHLY_YIELD_PER_KW = 120

# สัดส่วนการใช้ไฟช่วงกลางวัน — On-Grid หักลบได้เฉพาะส่วนนี้
DAYTIME_RATIO_PRESETS = {
    "บ้านไม่มีคนอยู่กลางวัน": 0.30,
    "บ้านทั่วไป": 0.50,
    "ร้านค้า/ออฟฟิศ": 0.70,
}
DEFAULT_DAYTIME_RATIO = 0.50

# ขนาดมาตรฐานที่ร้านติดตั้ง -> ราคารวมติดตั้ง (บาท) ระบบ On-Grid
PRICE_TABLE = {
    3: 105_000,
    5: 165_000,
    10: 300_000,
    15: 420_000,
    20: 540_000,
}

# ค่าไฟต่ำกว่านี้ ปกติคืนทุนเกิน 10 ปี — ให้เตือนลูกค้าตามตรง ไม่ดันขาย
MIN_WORTHWHILE_BILL = 2_000

# ขอบเขตที่ยอมรับ กัน LLM ส่งเลขเพี้ยนมา (เช่น หลักล้าน หรือติดลบ)
MIN_BILL = 100
MAX_BILL = 500_000


class EstimateError(ValueError):
    """ค่า input ไม่ผ่าน validation"""


def _pick_size(raw_kw: float) -> int:
    """เลือกขนาดมาตรฐานที่ใกล้ที่สุดจากด้านล่าง ไม่ปัดขึ้นเกินความจำเป็น

    ปัดขึ้นทำให้ไฟล้นทิ้ง คืนทุนช้า — นโยบายร้านคือแนะนำขนาดที่ไม่เกินการใช้จริง
    """
    sizes = sorted(PRICE_TABLE)
    chosen = sizes[0]
    for size in sizes:
        if size <= raw_kw + 0.5:
            chosen = size
    return chosen


def estimate(monthly_bill: float, daytime_ratio: float = DEFAULT_DAYTIME_RATIO) -> dict:
    """ประเมินขนาดระบบ ราคา และระยะเวลาคืนทุน จากค่าไฟเฉลี่ยต่อเดือน

    Args:
        monthly_bill: ค่าไฟเฉลี่ยต่อเดือน (บาท)
        daytime_ratio: สัดส่วนการใช้ไฟช่วงกลางวัน 0.1-0.9

    Returns:
        dict ผลการคำนวณทั้งหมด (ทุก key เป็นตัวเลขล้วน ไม่มีข้อความ)

    Raises:
        EstimateError ถ้า input นอกช่วงที่ยอมรับ
    """
    try:
        monthly_bill = float(monthly_bill)
        daytime_ratio = float(daytime_ratio)
    except (TypeError, ValueError):
        raise EstimateError("monthly_bill และ daytime_ratio ต้องเป็นตัวเลข")

    if not (MIN_BILL <= monthly_bill <= MAX_BILL):
        raise EstimateError(
            f"ค่าไฟต่อเดือนต้องอยู่ระหว่าง {MIN_BILL:,} ถึง {MAX_BILL:,} บาท (ได้รับ {monthly_bill:,.0f})"
        )
    if not (0.1 <= daytime_ratio <= 0.9):
        raise EstimateError("daytime_ratio ต้องอยู่ระหว่าง 0.1 ถึง 0.9")

    monthly_units = monthly_bill / ELECTRICITY_RATE
    daytime_units = monthly_units * daytime_ratio
    raw_kw = daytime_units / MONTHLY_YIELD_PER_KW

    recommended_kw = _pick_size(raw_kw)
    price = PRICE_TABLE[recommended_kw]

    # ประหยัดได้เท่ากับ min(ไฟที่ผลิตได้, ไฟที่ใช้กลางวัน) — ส่วนเกินไหลทิ้ง ไม่ได้เงินคืน
    produced_units = recommended_kw * MONTHLY_YIELD_PER_KW
    offset_units = min(produced_units, daytime_units)
    monthly_saving = offset_units * ELECTRICITY_RATE
    yearly_saving = monthly_saving * 12

    payback_years = price / yearly_saving if yearly_saving > 0 else float("inf")

    return {
        "monthly_bill": round(monthly_bill, 2),
        "daytime_ratio": daytime_ratio,
        "monthly_units": round(monthly_units, 1),
        "daytime_units": round(daytime_units, 1),
        "raw_kw": round(raw_kw, 2),
        "recommended_kw": recommended_kw,
        "price": price,
        "produced_units": round(produced_units, 1),
        "monthly_saving": round(monthly_saving, 2),
        "yearly_saving": round(yearly_saving, 2),
        "payback_years": round(payback_years, 1),
        "worthwhile": monthly_bill >= MIN_WORTHWHILE_BILL and payback_years <= 10,
    }


def format_th(result: dict) -> str:
    """แปลงผลคำนวณเป็นข้อความไทยพร้อมส่งให้ลูกค้า / Telegram"""
    lines = [
        f"ค่าไฟเฉลี่ย {result['monthly_bill']:,.0f} บาท/เดือน "
        f"(ประมาณ {result['monthly_units']:,.0f} หน่วย)",
        f"ใช้ไฟช่วงกลางวันประมาณ {result['daytime_ratio'] * 100:.0f}% "
        f"= {result['daytime_units']:,.0f} หน่วย/เดือน",
        f"ขนาดระบบที่แนะนำเบื้องต้น: {result['recommended_kw']} kW (On-Grid)",
        f"ราคาประเมิน: {result['price']:,} บาท",
        f"ประหยัดได้ประมาณ {result['monthly_saving']:,.0f} บาท/เดือน "
        f"({result['yearly_saving']:,.0f} บาท/ปี)",
        f"ระยะเวลาคืนทุนโดยประมาณ: {result['payback_years']} ปี",
    ]

    if not result["worthwhile"]:
        lines.append(
            "หมายเหตุ: จากค่าไฟระดับนี้ ระยะคืนทุนค่อนข้างนาน "
            "อาจยังไม่คุ้มในตอนนี้ แนะนำให้ปรึกษาก่อนตัดสินใจ"
        )

    lines.append(
        "ตัวเลขทั้งหมดเป็นการประเมินเบื้องต้น ราคาและขนาดจริง "
        "ต้องสำรวจหน้างานและตรวจสอบโดยผู้เชี่ยวชาญก่อนติดตั้ง"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    for bill in (1_000, 3_000, 6_000, 15_000):
        print(f"--- ค่าไฟ {bill:,} บาท ---")
        print(format_th(estimate(bill)))
        print()
