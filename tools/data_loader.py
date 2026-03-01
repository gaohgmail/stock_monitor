# -*- coding: utf-8 -*-
# tools/data_loader.py

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional

from tools.config import CALENDAR_PATH, DATA_DIR, CONCEPT_PATH, COL, COLUMN_MAPPING
from tools.utils import safe_read_csv, clean_dataframe, ensure_numeric_columns
from tools.cache_config import cached_data, CACHE_TTL

# ==================== 1. 基础辅助 (Helpers) ====================

@cached_data(ttl_seconds=CACHE_TTL['short'])
def get_current_trading_reference_date() -> date:
    """
    获取当前逻辑上的参考日期 (时区感知)
    规则：北京时间 9:00 前，参考日期为昨天；9:00 后为今天
    """
    # 北京时间 = UTC+8
    utc_now = datetime.now(timezone.utc)
    bj_now = utc_now.astimezone(timezone(timedelta(hours=8)))
    
    if bj_now.hour < 9:
        return (bj_now - timedelta(days=1)).date()
    return bj_now.date()


# ==================== 2. 交易日历 (Calendar) ====================

@cached_data(ttl_seconds=CACHE_TTL['short'])  # 使用短缓存，确保日期及时更新
def get_trade_dates(count: int = 30) -> List[datetime]:
    """
    获取最近 N 个有效交易日
    
    返回:
        按时间升序排列的 datetime 对象列表 (时间部分为 00:00:00)
    """
    if not CALENDAR_PATH.exists():
        # Fallback: 如果没有日历文件，返回最近的 N 天（简单回退模式）
        print(f"⚠️ 警告: 交易日历文件丢失 {CALENDAR_PATH}")
        return [datetime.combine(date.today() - timedelta(days=i), datetime.min.time()) for i in range(count)][::-1]

    # 读取日历
    df = safe_read_csv(CALENDAR_PATH)
    if df.empty:
        return []

    # 假设第一列是日期列，进行解析
    date_col = df.columns[0]
    # 统一转换为 datetime 对象
    all_dates = pd.to_datetime(df[date_col], errors='coerce').dropna().sort_values()
    
    # 过滤掉未来的日期（基于北京时间 9点 规则）
    ref_date = get_current_trading_reference_date()
    valid_dates = all_dates[all_dates.dt.date <= ref_date]
    
    # 取最后 count 个，转换为 datetime 对象
    return [datetime.combine(d.date(), datetime.min.time()) for d in valid_dates.tail(count).tolist()]


# ==================== 3. 市场数据读取 (Core Reader) ====================

@cached_data(ttl_seconds=CACHE_TTL['daily'])
def read_market_data(
    trade_date: datetime, 
    data_type: str,
    usecols: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    通用市场数据读取器
    
    功能：
    1. 调用 safe_read_csv 读取 (engine='c', dtype=str)
    2. 调用 clean_dataframe 标准化列名和代码
    3. 自动转换数值列 (价格、涨跌幅等)
    4. 自动转换单位 (万 -> 元)
    
    参数:
        trade_date: 交易日期
        data_type: 文件后缀类型 (如 '竞价行情', '收盘行情', '收盘涨跌停')
        usecols: (可选) 需要读取的列名列表，优化内存
    
    返回:
        清洗后的 DataFrame
    """
    # 路径构造
    date_str = trade_date.strftime('%Y-%m-%d')
    file_path = DATA_DIR / f"{date_str}_{data_type}.csv"
    
    # 1. 安全读取
    df = safe_read_csv(file_path, usecols=usecols)
    if df.empty:
        return df

    # 2. 清洗 (列名映射 + 代码标准化)
    df = clean_dataframe(df)

    # 3. 数值列批量转换
    # 定义需要转为 float 的列集合
    numeric_targets = [
        COL.STD_PRICE, COL.OPEN, COL.HIGH, COL.LOW, 
        COL.LIMIT_UP_PRICE, COL.LIMIT_DOWN_PRICE,
        COL.STD_AMOUNT, COL.PCT_CHG, 
        COL.VOLUME, COL.TURNOVER,
        COL.BID1_PRICE, COL.BID1_VOLUME  # 盘口数据
    ]
    # 只处理实际存在的列
    existing_numeric = [c for c in numeric_targets if c in df.columns]
    df = ensure_numeric_columns(df, existing_numeric)

    # 5. 单位转换说明
    # 原始CSV中列名可能包含"(万)"，但实际数据单位已经是"元"
    # 例如：成交额(万) 列的实际单位是元，不需要额外转换
    # 如果原始数据确实是万元单位，取消下面注释进行转换
    # wan_cols = [c for c in [COL.AMOUNT, COL.JJ_AMOUNT] if c in df.columns]
    # if wan_cols:
    #     df[wan_cols] = df[wan_cols] * 10000

    return df


# ==================== 4. 概念数据读取 ====================

@cached_data(ttl_seconds=CACHE_TTL['daily'])
def load_concept_data(trade_date: datetime) -> pd.DataFrame:
    """
    读取所属概念数据
    
    返回:
        DataFrame 包含 [股票代码, 所属概念, 所属行业] 列
    """
    if not CONCEPT_PATH.exists():
        return pd.DataFrame(columns=[COL.CODE, COL.CONCEPT, COL.INDUSTRY])
    
    df = safe_read_csv(CONCEPT_PATH)
    if df.empty:
        return df
    
    # 标准化列名
    df = clean_dataframe(df)
    
    # 确保有所需列
    if COL.CODE not in df.columns or COL.CONCEPT not in df.columns:
        return pd.DataFrame(columns=[COL.CODE, COL.CONCEPT, COL.INDUSTRY])
    
    # 返回包含行业列和涨停原因列的数据
    cols_to_return = [COL.CODE, COL.CONCEPT]
    if COL.INDUSTRY in df.columns:
        cols_to_return.append(COL.INDUSTRY)
    # 添加历史涨停原因类别列
    reason_cols = ['历史涨停原因类别', '涨停原因类别']
    for rc in reason_cols:
        if rc in df.columns:
            cols_to_return.append(rc)
    
    return df[cols_to_return]


# ==================== 5. 涨跌停数据读取 ====================

@cached_data(ttl_seconds=CACHE_TTL['daily'])
def load_limit_up_data(trade_date: datetime) -> pd.DataFrame:
    """
    读取涨跌停数据 (收盘涨跌停.csv)
    
    返回:
        DataFrame 包含涨停相关数据
    """
    df = read_market_data(trade_date, '收盘涨跌停')
    return df


# ==================== 6. 连板数据读取 ====================

@cached_data(ttl_seconds=CACHE_TTL['daily'])
def load_limit_up_boards(trade_date: datetime) -> pd.DataFrame:
    """
    读取连板梯队数据
    
    返回:
        DataFrame 包含连板天数、涨停原因等
    """
    df = read_market_data(trade_date, '连板梯队')
    return df


# ==================== 7. 连板数据获取 ====================

@cached_data(ttl_seconds=CACHE_TTL['daily'])
def get_lianban_data(trade_date: datetime) -> pd.DataFrame:
    """
    获取连板数据
    
    读取指定日期的收盘涨跌停数据，提取连板信息。
    
    参数:
        trade_date: 交易日期
    
    返回:
        包含连板数据的 DataFrame，列包括：股票代码、连续涨停天数、涨跌停
    """
    # 读取收盘涨跌停数据
    df_limit = read_market_data(trade_date, '收盘涨跌停')
    if df_limit.empty or '连续涨停天数' not in df_limit.columns:
        return pd.DataFrame()
    
    # 选择需要的列
    cols = ['股票代码', '连续涨停天数']
    if '股票代码' in df_limit.columns:
        cols = ['股票代码', '连续涨停天数']
    
    if '涨跌停' in df_limit.columns:
        cols.append('涨跌停')
    
    df_lianban = df_limit[cols].copy()
    df_lianban['连续涨停天数'] = pd.to_numeric(
        df_lianban['连续涨停天数'], errors='coerce'
    ).fillna(0).astype(int)
    
    return df_lianban
