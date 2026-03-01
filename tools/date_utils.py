# tools/date_utils.py
from datetime import datetime, date
from typing import List, Union, Dict

def ensure_datetime(date_obj: Union[datetime, date, str]) -> datetime:
    """鲁棒的日期转换工具"""
    if isinstance(date_obj, datetime):
        return date_obj
    if isinstance(date_obj, date):
        return datetime.combine(date_obj, datetime.min.time())
    if isinstance(date_obj, str):
        return datetime.strptime(date_obj, '%Y-%m-%d')
    raise TypeError(f"Unsupported date type: {type(date_obj)}")

def get_date_context(
    date_list: List[date], 
    selected_date: Union[date, datetime] = None
) -> Dict:
    """
    纯函数：根据给定的日期列表计算上下文
    不再内部调用 get_trade_dates，解耦依赖
    """
    if not date_list:
        return {}
    
    # 确保格式统一
    date_list = sorted([d if isinstance(d, date) else d.date() for d in date_list])
    
    if selected_date:
        target = selected_date.date() if isinstance(selected_date, datetime) else selected_date
    else:
        target = date_list[-1]
    
    # 使用 bisect 查找索引 (虽然列表短，但这是好习惯)
    try:
        idx = date_list.index(target)
    except ValueError:
        # 如果选中日期不在交易日历中（比如周六），找最近的前一个交易日
        import bisect
        idx = bisect.bisect_right(date_list, target) - 1
        if idx < 0: idx = 0
    
    today = date_list[idx]
    prev = date_list[idx - 1] if idx > 0 else date_list[0]
    next_d = date_list[idx + 1] if idx < len(date_list) - 1 else date_list[-1]
    
    return {
        'date_list': date_list,
        'today': today,
        'yesterday': prev,
        'next_day': next_d,
        'today_datetime': ensure_datetime(today),
        'yesterday_datetime': ensure_datetime(prev)
    }