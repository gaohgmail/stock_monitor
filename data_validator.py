# -*- coding: utf-8 -*-
"""
业务规则验证器
"""

from datetime import datetime, time
from pathlib import Path
from tools.config import DATA_DIR


class DataValidator:
    """业务规则验证器"""

    @staticmethod
    def check_close_time(target_date: datetime) -> bool:
        """判断是否满足查看收盘数据的时间条件 (T日15:00后)"""
        now = datetime.now()
        target_date_obj = target_date.date() if isinstance(target_date, datetime) else target_date
        
        if target_date_obj < now.date():
            return True
        if target_date_obj == now.date():
            return now.time() >= time(15, 0)
        return False

    @staticmethod
    def check_raw_data_exists(target_date: datetime, data_type: str) -> bool:
        """检查基础行情文件是否存在"""
        date_str = target_date.strftime('%Y-%m-%d')
        file_path = DATA_DIR / f"{date_str}_{data_type}.csv"
        return file_path.exists()
