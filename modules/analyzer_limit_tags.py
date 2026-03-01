# -*- coding: utf-8 -*-
"""
涨停标签分析组件
功能：生成涨停股票的标签分析（竞价/收盘），支持连板、首板分类

使用示例:
    from modules.analyzer_limit_tags import analyze_limit_up_tags, save_limit_up_results
    
    # 分析收盘涨停
    df = analyze_limit_up_tags(datetime(2026, 2, 6), stage='收盘')
    
    # 保存结果
    save_limit_up_results(df, pd.DataFrame(), datetime(2026, 2, 6))
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple

from tools.config import COL
from tools.utils import calculate_limit_up_numpy
from tools.data_loader import read_market_data, get_lianban_data, get_trade_dates
from tools.date_utils import ensure_datetime
from tools.save_utils import save_limit_up_data


# =============================================================================
# 核心分析函数
# =============================================================================

def analyze_limit_up_tags(today_date: datetime, prev_date: datetime = None,
                          stage: str = '收盘') -> pd.DataFrame:
    """
    分析涨停股票标签

    参数:
        today_date: 今日日期
        prev_date: 昨日日期（可选，自动计算）
        stage: '竞价' 或 '收盘'

    返回:
        DataFrame 包含涨停股票的标签信息:
        - 股票代码、股票简称
        - 连续涨停天数、昨日连板天数（收盘）
        - 涨幅、放量倍数、封单(亿)
    """
    today_date = ensure_datetime(today_date)

    if prev_date is None:
        prev_date = _get_prev_trade_date(today_date)
    else:
        prev_date = ensure_datetime(prev_date)

    if stage == '竞价':
        return _analyze_auction_limit_up(today_date, prev_date)
    else:
        return _analyze_close_limit_up(today_date, prev_date)


def analyze_limit_up_comparison(today_date: datetime,
                                prev_date: datetime = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    同时分析竞价和收盘的涨停数据

    返回:
        (df_auction, df_close): 竞价和收盘的涨停分析结果
    """
    df_auction = analyze_limit_up_tags(today_date, prev_date, stage='竞价')
    df_close = analyze_limit_up_tags(today_date, prev_date, stage='收盘')
    return df_auction, df_close


# =============================================================================
# 内部实现
# =============================================================================

def _analyze_auction_limit_up(today_date: datetime, prev_date: datetime) -> pd.DataFrame:
    """分析竞价阶段涨停"""
    df_today = read_market_data(today_date, '竞价行情')
    df_yest_close = read_market_data(prev_date, '收盘行情')
    df_yest_auc = read_market_data(prev_date, '竞价行情')

    if df_today.empty:
        return pd.DataFrame()

    # 注入昨日连板数据
    df_lianban = get_lianban_data(prev_date)
    if not df_lianban.empty:
        cols_to_merge = [COL.CODE, COL.CONSECUTIVE_LIMIT_UP_DAYS]
        if COL.LIMIT_UP_DOWN_STATUS in df_lianban.columns:
            cols_to_merge.append(COL.LIMIT_UP_DOWN_STATUS)
        df_today = df_today.merge(df_lianban[cols_to_merge], on=COL.CODE, how='left')

    # 计算基础特征
    df_calc = _prepare_data(df_today, df_yest_auc, df_yest_close, is_auction=True)

    # 涨停判定
    prices = df_calc[COL.STD_PRICE].values
    limit_ups = df_calc[COL.LIMIT_UP_PRICE].values
    chgs = df_calc['pct_chg'].values
    is_limit_up = calculate_limit_up_numpy(prices, limit_ups, chgs)

    # 竞价涨停天数+1
    days = df_calc['days'].astype(int) + 1

    # 计算封单额
    lock_amount = _calculate_lock_amount(df_calc, smart_mode=False)

    # 构建输出
    output = pd.DataFrame({
        '股票代码': df_calc[COL.CODE],
        '股票简称': df_calc[COL.NAME],
        '连续涨停天数': days,
        '竞价涨幅': chgs,
        '竞价放量倍数': df_calc['ratio'],
        COL.LOCK_AMOUNT: lock_amount,
        COL.STD_AMOUNT: df_calc[COL.STD_AMOUNT] if COL.STD_AMOUNT in df_calc.columns else 0,
    })

    return output[is_limit_up].reset_index(drop=True)


def _analyze_close_limit_up(today_date: datetime, prev_date: datetime) -> pd.DataFrame:
    """分析收盘阶段涨停"""
    df_today = read_market_data(today_date, '收盘行情')
    df_yest_close = read_market_data(prev_date, '收盘行情')

    if df_today.empty:
        return pd.DataFrame()

    # 注入今日连板数据
    df_lianban_today = get_lianban_data(today_date)
    if not df_lianban_today.empty:
        cols = [COL.CODE, COL.CONSECUTIVE_LIMIT_UP_DAYS, COL.LIMIT_UP_DOWN_STATUS]
        cols = [c for c in cols if c in df_lianban_today.columns]
        df_today = df_today.merge(df_lianban_today[cols], on=COL.CODE, how='left')

    # 获取昨日连板数据
    df_lianban_yest = get_lianban_data(prev_date)
    if not df_lianban_yest.empty:
        yest_map = df_lianban_yest.set_index(COL.CODE)[COL.CONSECUTIVE_LIMIT_UP_DAYS]
        days_yest_series = df_today[COL.CODE].map(yest_map).fillna(0)
    else:
        days_yest_series = pd.Series(0, index=df_today.index)

    # 计算基础特征
    df_calc = _prepare_data(df_today, df_yest_close, None, is_auction=False)

    # 涨停判定（标记为涨停 + 涨幅>9%过滤ST）
    chgs = df_calc['pct_chg'].values
    is_limit_up = (COL.LIMIT_UP_DOWN_STATUS in df_calc.columns) & \
                  (df_calc[COL.LIMIT_UP_DOWN_STATUS] == '涨停') & \
                  (chgs > 9.0)

    # 计算封单额
    lock_amount = _calculate_lock_amount(df_calc, smart_mode=True)

    # 构建输出
    output = pd.DataFrame({
        '股票代码': df_calc[COL.CODE],
        '股票简称': df_calc[COL.NAME],
        '连续涨停天数': df_calc['days'].astype(int),
        '昨日连板天数': days_yest_series.astype(int),
        '收盘涨幅': chgs,
        '放量倍数': df_calc['ratio'],
        COL.LOCK_AMOUNT: lock_amount,
        COL.STD_AMOUNT: df_calc[COL.STD_AMOUNT] if COL.STD_AMOUNT in df_calc.columns else 0,
    })

    return output[is_limit_up].reset_index(drop=True)


# =============================================================================
# 辅助函数
# =============================================================================

def _prepare_data(df_today: pd.DataFrame, df_yest: pd.DataFrame,
                  df_yest_close: Optional[pd.DataFrame], is_auction: bool) -> pd.DataFrame:
    """准备数据"""
    amt_col = COL.STD_AMOUNT

    df = df_today.merge(
        df_yest[[COL.CODE, amt_col]].rename(columns={amt_col: 'amt_prev'}),
        on=COL.CODE, how='left'
    )

    yest_detail = df_yest_close if is_auction and df_yest_close is not None else df_yest

    yest_cols = {
        COL.HIGH: 'y_high',
        COL.STD_PRICE: 'y_price',
        COL.LOW: 'y_low',
        COL.LIMIT_UP_PRICE: 'y_limit',
        COL.PCT_CHG: 'y_pct'
    }
    df = df.merge(
        yest_detail[[COL.CODE] + list(yest_cols.keys())].rename(columns=yest_cols),
        on=COL.CODE, how='left'
    )

    numeric_cols = ['amt_prev', 'y_high', 'y_price', 'y_low', 'y_limit', 'y_pct']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['amt_now'] = pd.to_numeric(df[amt_col], errors='coerce').fillna(0)
    df['amt_prev'] = df['amt_prev'].where(df['amt_prev'] >= 1e6, 9.9e5)

    df['ratio'] = df['amt_now'] / df['amt_prev']
    df['pct_chg'] = pd.to_numeric(df[COL.PCT_CHG], errors='coerce').fillna(0)
    df['days'] = pd.to_numeric(df.get(COL.CONSECUTIVE_LIMIT_UP_DAYS, 0),
                               errors='coerce').fillna(0)

    return df


def _calculate_lock_amount(df_calc: pd.DataFrame, smart_mode: bool = False) -> np.ndarray:
    """计算封单额（亿元）"""
    bid1_price = pd.to_numeric(df_calc.get(COL.BID1_PRICE, 0), errors='coerce').fillna(0)
    bid1_volume = pd.to_numeric(df_calc.get(COL.BID1_VOLUME, 0), errors='coerce').fillna(0)

    if smart_mode:
        ask1_price = pd.to_numeric(df_calc.get(COL.ASK1_PRICE, 0), errors='coerce').fillna(0)
        ask1_volume = pd.to_numeric(df_calc.get(COL.ASK1_VOLUME, 0), errors='coerce').fillna(0)
        has_ask1 = (ask1_price > 0) & (ask1_volume > 0)
        return np.where(
            has_ask1,
            -ask1_price * ask1_volume / 1e8,
            bid1_price * bid1_volume / 1e8
        )
    else:
        return bid1_price * bid1_volume / 1e8


def _get_prev_trade_date(today_date: datetime) -> datetime:
    """获取前一个交易日"""
    trade_dates = get_trade_dates(count=30)
    for d in sorted(trade_dates, reverse=True):
        if d < today_date:
            return d
    return today_date - timedelta(days=1)


# =============================================================================
# 保存功能
# =============================================================================

def save_limit_up_results(df_auction: pd.DataFrame, df_close: pd.DataFrame,
                          today_date: datetime, output_dir: str = None):
    """
    保存涨停分析结果到CSV

    参数:
        df_auction: 竞价涨停数据
        df_close: 收盘涨停数据
        today_date: 日期
        output_dir: 输出目录（默认analysis_results/market_daily）
    """
    save_limit_up_data(df_auction, df_close, today_date, output_dir)
    print(f"[{today_date.date()}] 涨停分析结果已成功保存")
