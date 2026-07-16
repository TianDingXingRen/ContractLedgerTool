"""Rule based payment clause extraction.

The extractor intentionally produces editable draft rows. It is conservative:
clear dates and percentages are used when present, fuzzy clauses stay pending
with their original text preserved for manual review.
"""

import math
import re
from datetime import datetime, timedelta
from decimal import Decimal

from docx import Document

from utils.field_utils import normalize_date

# 付款计划提取上限（防止异常文档产生海量计划条目）
MAX_EXTRACTED_PLANS = 30

PAYMENT_KEYWORDS = (
    '付款', '支付', '付清', '结算', '预付款', '定金', '尾款', '余款',
    '质保金', '保证金', '货款', '价款', '款项', '验收', '发票',
    '开票', '货到', '到货',
)
STRONG_PAYMENT_KEYWORDS = (
    '付款', '支付', '付清', '结算', '预付款', '定金', '尾款', '余款',
    '质保金', '保证金', '货款', '价款', '款项',
)
PAYMENT_ACTION_KEYWORDS = (
    '付款', '支付', '付清', '结算', '预付款', '预付', '定金', '尾款',
    '余款', '质保金', '保证金', '一次总付', '分期支付',
)
TRIGGER_ONLY_KEYWORDS = ('验收', '发票', '开票', '货到', '到货')
PLANISH_NO_MONEY_KEYWORDS = (
    '一次总付', '分期支付', '预付款', '尾款', '余款', '质保金',
    '付款期限', '结算方式',
)
EXCLUDE_PAYMENT_KEYWORDS = (
    '不得', '报销', '赔偿', '违约金', '罚金', '滞纳金', '责任方',
)
PRICE_SUMMARY_KEYWORDS = (
    '合同总价款', '合同款项', '订购', '不含税金额', '税额',
    '增值税', '税率', '含税', '大写', '小写',
)

EVENT_LABELS = {
    'contract_signed': '合同签订',
    'effective': '合同生效',
    'invoice_received': '收到发票',
    'arrival': '到货',
    'shipment': '发货',
    'delivery': '交付',
    'acceptance': '验收合格',
    'warranty_end': '质保期满',
    'fixed_date': '固定日期',
    'other': '其他',
}


def extract_docx_text(path):
    doc = Document(path)
    try:
        parts = []
        for para in doc.paragraphs:
            text = (para.text or '').strip()
            if text:
                parts.append(text)
        for table in doc.tables:
            for row in table.rows:
                cells = []
                for cell in row.cells:
                    value = ''.join(p.text or '' for p in cell.paragraphs).strip()
                    if value:
                        cells.append(value)
                if cells:
                    parts.append(' | '.join(cells))
        return '\n'.join(parts)
    finally:
        del doc


def extract_payment_plans(text, contract_amount=None, sign_date=''):
    snippets = _payment_snippets(text or '')
    plans = []
    for snippet in snippets:
        for segment in _split_segments(snippet):
            plans.extend(_parse_segment(segment, contract_amount, sign_date))

    deduped = []
    seen = set()
    for plan in plans:
        key = (
            plan.get('phase_name'),
            plan.get('ratio'),
            plan.get('due_amount'),
            plan.get('due_date'),
            plan.get('source_text'),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(plan)
    return _trim_plans(deduped, contract_amount)[:MAX_EXTRACTED_PLANS]


def _payment_snippets(text):
    normalized = re.sub(r'\s+', ' ', text)
    rough = re.split(r'[。；;\n\r]+', normalized)
    snippets = []
    for chunk in rough:
        chunk = chunk.strip()
        if len(chunk) < 4:
            continue
        if _is_candidate_clause(chunk):
            snippets.append(chunk)
    return snippets


def _split_segments(snippet):
    parts = [p.strip() for p in re.split(r'[；;。]+', snippet) if p.strip()]
    useful = []
    for part in parts:
        if _is_candidate_clause(part):
            useful.append(part)
    return useful or [snippet]


def _is_candidate_clause(text):
    if any(k in text for k in EXCLUDE_PAYMENT_KEYWORDS):
        return False
    if _looks_like_price_summary(text):
        return False
    has_money = bool(_extract_ratios(text) or _extract_amounts(text))
    has_action = any(k in text for k in PAYMENT_ACTION_KEYWORDS)
    has_strong = any(k in text for k in STRONG_PAYMENT_KEYWORDS)
    has_trigger = any(k in text for k in TRIGGER_ONLY_KEYWORDS)
    has_planish = any(k in text for k in PLANISH_NO_MONEY_KEYWORDS)
    if has_money and (has_action or (has_strong and has_trigger)):
        return True
    if has_planish:
        return True
    if has_action and has_trigger:
        return True
    return False


def _looks_like_price_summary(text):
    has_price_summary = any(k in text for k in PRICE_SUMMARY_KEYWORDS)
    if not has_price_summary:
        return False
    has_action = any(k in text for k in PAYMENT_ACTION_KEYWORDS)
    if has_action:
        return False
    return bool(_extract_amounts(text) or _extract_ratios(text))


def _parse_segment(segment, contract_amount, sign_date):
    ratios = _extract_ratios(segment)
    amounts = _extract_amounts(segment)
    explicit_date = _extract_date(segment, sign_date)
    trigger_event = _detect_event(segment, explicit_date)
    trigger_days = _extract_days(segment)
    due_date = explicit_date
    if not due_date and sign_date and trigger_event in ('contract_signed', 'effective'):
        due_date = _add_days(sign_date, trigger_days or 0)

    plans = []
    if ratios:
        for idx, ratio in enumerate(ratios):
            amount = None
            if contract_amount is not None:
                amount = round(float(contract_amount) * ratio / 100, 2)
            plans.append(
                _make_plan(
                    segment=segment,
                    phase_name=_phase_name(segment, idx),
                    trigger_event=trigger_event,
                    trigger_days=trigger_days,
                    due_date=due_date,
                    ratio=ratio,
                    due_amount=amount,
                    confidence=_confidence(segment, ratio, amount, due_date, trigger_event),
                )
            )
    elif amounts:
        for idx, amount in enumerate(amounts):
            plans.append(
                _make_plan(
                    segment=segment,
                    phase_name=_phase_name(segment, idx),
                    trigger_event=trigger_event,
                    trigger_days=trigger_days,
                    due_date=due_date,
                    ratio=None,
                    due_amount=amount,
                    confidence=_confidence(segment, None, amount, due_date, trigger_event),
                )
            )
    else:
        plans.append(
            _make_plan(
                segment=segment,
                phase_name=_phase_name(segment, 0),
                trigger_event=trigger_event,
                trigger_days=trigger_days,
                due_date=due_date,
                ratio=None,
                due_amount=None,
                confidence='low',
            )
        )
    return plans


def _make_plan(segment, phase_name, trigger_event, trigger_days, due_date, ratio, due_amount, confidence):
    payment_type = 'fixed_date' if due_date and trigger_event == 'fixed_date' else 'conditional'
    return {
        'phase_name': phase_name,
        'payment_type': payment_type,
        'trigger_event': EVENT_LABELS.get(trigger_event, '其他'),
        'trigger_days': trigger_days,
        'due_date': due_date,
        'ratio': ratio,
        'due_amount': due_amount,
        'paid_amount': 0,
        'condition_text': segment,
        'source_text': segment,
        'confidence': confidence,
        'confirm_status': 'pending',
        'payment_status': 'unpaid',
    }


def _extract_ratios(text):
    ratios = []
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*%', text):
        context = text[max(0, m.start() - 8):min(len(text), m.end() + 8)]
        if any(k in context for k in ('增值税', '税率', '税额')):
            continue
        ratios.append(float(m.group(1)))
    for m in re.finditer(r'百分之([零一二三四五六七八九十百两\d.]+)', text):
        parsed = _parse_cn_number(m.group(1))
        if parsed is not None:
            ratios.append(float(parsed))
    return ratios


def _extract_amounts(text):
    amounts = []
    pattern = r'(?:人民币|RMB|[￥¥])?\s*([0-9][0-9,]*(?:\.\d+)?)\s*(亿元|万元|千元|百元|元)'
    for m in re.finditer(pattern, text, re.I):
        # 排除已支付/已预付/实付等上下文
        prefix = text[max(0, m.start() - 10):m.start()]
        if any(kw in prefix for kw in ('已付', '已支付', '已预付', '实付', '扣减')):
            continue
        raw = m.group(1).replace(',', '')
        # 拒绝超大数字（防止 float overflow → inf）
        if len(raw.replace('.', '')) > 15:
            continue
        try:
            value = float(raw)
        except (ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue
        unit = m.group(2)
        if unit == '亿元':
            value *= 100000000
        elif unit == '万元':
            value *= 10000
        elif unit == '千元':
            value *= 1000
        elif unit == '百元':
            value *= 100
        amounts.append(round(value, 2))
    return amounts


def _extract_days(text):
    m = re.search(r'(\d+)\s*(?:个)?(?:工作日|日|天)\s*内?', text)
    if m:
        return int(m.group(1))
    return None


def _extract_date(text, sign_date=''):
    result = normalize_date(text)
    if result:
        return result

    m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if m:
        year = (sign_date or '')[:4] or str(datetime.now().year)
        month, day = m.groups()
        try:
            return datetime(int(year), int(month), int(day)).strftime('%Y-%m-%d')
        except ValueError:
            return ''
    return ''


def _safe_float(val, default=0.0):
    """安全转换为浮点数，失败返回默认值。"""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _trim_plans(plans, contract_amount):
    cleaned = []
    for plan in plans:
        amount = plan.get('due_amount')
        ratio = plan.get('ratio')
        source = plan.get('source_text') or ''
        if amount is None and ratio is None and not any(k in source for k in PAYMENT_ACTION_KEYWORDS):
            continue
        if _looks_like_price_summary(source):
            continue
        cleaned.append(plan)

    try:
        contract_total = Decimal(str(contract_amount))
    except Exception:
        return cleaned
    if contract_total <= 0:
        return cleaned

    def score(plan):
        source = plan.get('source_text') or ''
        value = 0
        if plan.get('due_date'):
            value += 4
        if plan.get('trigger_event') not in ('其他', '', None):
            value += 2
        if plan.get('ratio') is not None:
            value += 2
        if any(k in source for k in ('第', '笔', '期', '分期', '尾款', '预付款', '质保金')):
            value += 2
        if plan.get('confidence') == 'high':
            value += 2
        elif plan.get('confidence') == 'medium':
            value += 1
        return value

    # 使用 Decimal 精确求和与比较，容差 5%
    total_due = Decimal('0')
    for p in cleaned:
        amt = p.get('due_amount')
        if amt is not None:
            total_due += Decimal(str(amt))
    tolerance = contract_total * Decimal('0.05')
    if total_due <= contract_total + tolerance:
        return cleaned

    selected = []
    running = Decimal('0')
    for plan in sorted(cleaned, key=score, reverse=True):
        amt = Decimal(str(_safe_float(plan.get('due_amount'))))
        if amt and running + amt > contract_total + tolerance:
            continue
        selected.append(plan)
        running += amt
    # 贪心裁剪后结果为空时回退到原始列表，避免静默丢失所有计划
    if not selected and cleaned:
        import logging
        logging.getLogger('contract_tool').warning(
            '付款计划裁剪后结果为空（合同金额=%s, 原计划数=%d），保留全部计划待人工确认',
            contract_total, len(cleaned),
        )
        cleaned.sort(key=lambda p: (p.get('due_date') or '9999-12-31', p.get('source_text') or ''))
        return cleaned
    # 按 due_date 排序，若相同则按 source_text 保证稳定性
    selected.sort(key=lambda p: (p.get('due_date') or '9999-12-31', p.get('source_text') or ''))
    return selected


def _detect_event(text, explicit_date=''):
    # 先检测触发事件关键词（即使有日期也保留语义）
    if '签订' in text:
        return 'contract_signed'
    if '生效' in text:
        return 'effective'
    if '发票' in text or '开票' in text:
        return 'invoice_received'
    if '验收' in text:
        return 'acceptance'
    if '货到' in text or '到货' in text:
        return 'arrival'
    if '发货' in text:
        return 'shipment'
    if '交付' in text:
        return 'delivery'
    if '质保' in text:
        return 'warranty_end'
    if explicit_date:
        return 'fixed_date'
    return 'other'


def _phase_name(text, index):
    if '预付款' in text or '预付' in text or '定金' in text:
        return '预付款'
    if '到货' in text or '货到' in text:
        return '到货款'
    if '验收' in text:
        return '验收款'
    if '质保' in text:
        return '质保金'
    if '尾款' in text or '余款' in text:
        return '尾款'
    if '进度' in text:
        return '进度款'
    if index:
        return f'第{index + 1}期款'
    return '付款'


def _confidence(text, ratio, amount, due_date, trigger_event):
    has_money = ratio is not None or amount is not None
    has_condition = trigger_event not in ('other', '') or bool(due_date)
    if has_money and has_condition:
        return 'high'
    if has_money:
        return 'medium'
    if any(k in text for k in ('付款', '支付', '结算')):
        return 'low'
    return 'low'


def _add_days(date_text, days):
    try:
        base = datetime.strptime(date_text[:10], '%Y-%m-%d')
        return (base + timedelta(days=int(days or 0))).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return ''


def _parse_cn_number(text):
    """解析中文数字字符串，支持 百/千/万/亿。

    示例: "一百二十" → 120, "五万三千" → 53000,
          "一亿二千三百万" → 123000000
    """
    if re.fullmatch(r'\d+(?:\.\d+)?', text):
        return float(text)

    digit_map = {
        '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
        '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
    }
    # 单位：十/百/千 在万以下累积，万/亿 作为分段边界
    unit_map = {'十': 10, '百': 100, '千': 1000}
    section_units = {'万': 10000, '亿': 100000000}

    result = 0      # 亿/万级别累计
    section = 0      # 当前万以下段的累计
    digit = 0        # 当前读取的数字

    for ch in text:
        if ch in digit_map:
            digit = digit_map[ch]
        elif ch in unit_map:
            section += (digit or 1) * unit_map[ch]
            digit = 0
        elif ch in section_units:
            section = (section + digit) * section_units[ch]
            result += section
            section = 0
            digit = 0
        elif ch == '零':
            digit = 0  # 零不改变数值，只占位
        else:
            return None  # 无法识别的字符

    result += section + digit
    return float(result) if result > 0 else None
