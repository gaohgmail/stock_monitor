# modules/analyzer_market.py
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from modules.data_loader import read_market_data
import streamlit as st


def fast_daily_calc(df: pd.DataFrame, prefix: str):
    """
    使用 NumPy 向量化提速计算
    """
    if df.empty: return {}

    # 获取标准列名
    amt_col = f"{prefix}金额"
    price_col = f"{prefix}价"
    chg_col = '涨跌幅'
    name_col = '股票简称'
    code_col = '股票代码'

    # 预检查必需列，防止报错
    required = [amt_col, price_col, chg_col, name_col, code_col, '涨停价', '跌停价']
    if not all(c in df.columns for c in required): return {}

    # 转为 NumPy 数组提升性能
    codes = df[code_col].values.astype(str)
    amts = df[amt_col].values
    chgs = df[chg_col].values
    names = df[name_col].values.astype(str)
    prices = df[price_col].values
    limit_up_prices = df['涨停价'].values
    limit_down_prices = df['跌停价'].values

    # 构造常用布尔掩码
    mask_sh = np.char.startswith(codes, 'sh6')
    mask_cyb = np.char.startswith(codes, 'sz3')
    # 1. 强化 ST 过滤：涵盖 ST, *ST, SST 以及可能的大小写
    # NumPy 向量化：先转小写，再查是否存在 'st'
    names_lower = np.char.lower(names)
    mask_not_st = (np.char.find(names_lower, 'st') == -1)
    
    # 2. 极高精度涨跌停判定 (使用 0.001 避免浮点数漂移误差)
    # 增加 price > 0 判定，防止停牌股干扰
    # 1. 极高精度价格判定 (0.001)
    # 2. 叠加涨跌幅阈值 (大于 9% 或 小于 -9%)
    is_limit_up = (prices > 0) & (np.abs(prices - limit_up_prices) < 0.001) & (chgs > 9)
    is_limit_down = (prices > 0) & (np.abs(prices - limit_down_prices) < 0.001) & (chgs < -9)

    # 3. 情绪计数逻辑 (确保仅在 mask_not_st 范围内)
    m_valid = mask_not_st
    
    # 涨停/跌停数统计
    count_limit_up = np.sum(is_limit_up & m_valid)
    count_limit_down = np.sum(is_limit_down & m_valid)
    
    # 核心统计计算
    total_amt = np.sum(amts) / 1e8
    sh_amt = np.sum(amts[mask_sh]) / 1e8
    cyb_amt = np.sum(amts[mask_cyb]) / 1e8

    # 情绪指标计数 (在 not_st 掩码下计算)
    m_valid = mask_not_st
    m_sh_valid = mask_not_st & mask_sh
    m_cyb_valid = mask_not_st & mask_cyb

    raw_stats = {
        '总额': total_amt,
        '上海额': sh_amt,
        '创业额': cyb_amt,
        '强力': np.sum((chgs >= 7) & m_valid),
        '极弱': np.sum((chgs <= -7) & m_valid),
        '涨停': count_limit_up),
        '跌停': count_limit_down,
        '上涨数': np.sum((chgs > 0) & m_valid),
        '下跌数': np.sum((chgs < 0) & m_valid),
        '沪涨': np.sum((chgs > 0) & m_sh_valid),
        '沪跌': np.sum((chgs < 0) & m_sh_valid),
        '创涨': np.sum((chgs > 0) & m_cyb_valid),
        '创跌': np.sum((chgs < 0) & m_cyb_valid)
    }
    return {f"{prefix}_{k}": v for k, v in raw_stats.items()}

def process_single_date(d):
    """单日处理单元"""
    try:
        df_jj = read_market_data(d, '竞价行情')
        df_sp = read_market_data(d, '收盘行情')
        if df_jj.empty and df_sp.empty: return None
        
        res_jj = fast_daily_calc(df_jj, prefix="竞价")
        res_sp = fast_daily_calc(df_sp, prefix="收盘")
        
        combined = {'日期': d.strftime('%Y-%m-%d'), '_raw_date': d}
        combined.update(res_jj)
        combined.update(res_sp)
        return combined
    except Exception: return None
#@st.cache_data
@st.cache_data(ttl=20000)
def get_sentiment_trend_report(date_list: list):
    """生成趋势表，补全所有 49 列指标"""
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = [r for r in executor.map(process_single_date, date_list) if r is not None]
    
    if not results: return pd.DataFrame()
    
    trend_df = pd.DataFrame(results).sort_values('_raw_date')

    # 批量计算衍生指标（确保竞价/收盘各 24 列）
    for p in ['竞价', '收盘']:
        # 1. 资金维度 (4列)
        trend_df[f'{p}_资金增减'] = trend_df[f'{p}_总额'].diff()
        trend_df[f'{p}_增减幅'] = trend_df[f'{p}_总额'].pct_change()
        trend_df[f'{p}_上海差值'] = trend_df[f'{p}_上海额'].diff()   # 之前漏掉的
        trend_df[f'{p}_创业差值'] = trend_df[f'{p}_创业额'].diff()   # 之前漏掉的

        # 2. 涨跌比维度 (3列)
        trend_df[f'{p}_全场涨跌比'] = trend_df[f'{p}_上涨数'] / trend_df[f'{p}_下跌数'].replace(0, 1)
        trend_df[f'{p}_上海涨跌比'] = trend_df[f'{p}_沪涨'] / trend_df[f'{p}_沪跌'].replace(0, 1) # 之前漏掉的
        trend_df[f'{p}_创业涨跌比'] = trend_df[f'{p}_创涨'] / trend_df[f'{p}_创跌'].replace(0, 1) # 之前漏掉的

        # 3. 情绪波动维度 (4列)
        trend_df[f'{p}_涨停_diff'] = trend_df[f'{p}_涨停'].diff().fillna(0).astype(int)
        trend_df[f'{p}_跌停_diff'] = trend_df[f'{p}_跌停'].diff().fillna(0).astype(int)
        trend_df[f'{p}_强力_diff'] = trend_df[f'{p}_强力'].diff().fillna(0).astype(int)
        trend_df[f'{p}_极弱_diff'] = trend_df[f'{p}_极弱'].diff().fillna(0).astype(int)

    # 最终列顺序整理（非必须，但有助于对齐）
    return trend_df.drop(columns=['_raw_date']).reset_index(drop=True)
