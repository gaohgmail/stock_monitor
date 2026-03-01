# -*- coding: utf-8 -*-
# modules/analyzer_market.py
# 高性能市场情绪分析引擎 - 全向量化优化版本 (集成养家心法指标)

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import time

from tools.config import (
    DATA_DIR, 
    SENTIMENT_TREND_PATH, 
    MARKET_REPORT_DIR,
    COL
)
from tools.data_loader import read_market_data, get_trade_dates # 假设有获取交易日历的工具
from tools.date_utils import get_date_context, ensure_datetime
from tools.utils import calculate_limit_up_numpy


# ==================== 性能优化配置 ====================

_ST_MASK_PATTERNS = ['ST', '*ST', 'SST']
_MARKET_MASKS_CACHE = {}

# 新增常量定义
TOP_AMOUNT_N = 15  # 成交额前N
TOP_RETURN_N = 20  # 涨跌幅前N

# ==================== 0. 养家心法核心指标计算 (新增模块) ====================

def _get_yesterday_top_lists(current_date: datetime) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    【新增】获取上一交易日的 Top15(金额) 和 Top20(涨幅) 股票数据
    使用交易日历来准确获取上一个交易日
    """
    # 获取交易日历并使用 date_utils 找到昨日
    trade_dates = get_trade_dates(count=60)
    date_list = [d.date() for d in trade_dates]
    yesterday = get_date_context(date_list, current_date)['yesterday']
    
    # 读取昨日的收盘数据
    df_prev = read_market_data(ensure_datetime(yesterday), '收盘行情')
    
    if df_prev.empty:
        return None, None

    # 计算榜单
    df_top_amt = df_prev.nlargest(TOP_AMOUNT_N, COL.STD_AMOUNT)[[COL.CODE, COL.YESTERDAY_CLOSE, COL.STD_PRICE]].copy() # 保留昨收盘用于计算
    df_top_ret = df_prev.nlargest(TOP_RETURN_N, COL.PCT_CHG)[[COL.CODE, COL.YESTERDAY_CLOSE, COL.STD_PRICE]].copy()
    
    # 统一重命名方便后续合并
    df_top_amt.rename(columns={COL.STD_PRICE: '昨日收盘价_Ref'}, inplace=True)
    df_top_ret.rename(columns={COL.STD_PRICE: '昨日收盘价_Ref'}, inplace=True)
    
    return df_top_amt, df_top_ret

def _calc_yangjia_metrics(df_today: pd.DataFrame, 
                          df_ref: pd.DataFrame, 
                          prefix: str, 
                          metric_type: str) -> Dict[str, float]:
    """
    【新增】计算核心情绪指标 (溢价率/赚钱效应/承接力)
    
    Args:
        df_today: 今日数据 (竞价或收盘)
        df_ref: 昨日参考榜单 (Top15金额 或 Top20涨幅)
        prefix: 输出前缀 (如 '竞价', '收盘')
        metric_type: 指标类型后缀 (如 '龙头', '妖股')
    """
    if df_ref is None or df_today.empty:
        return {}

    # 1. 筛选出今日在榜单中的票
    # 使用 merge 来获取对应的“昨日收盘价”，这比 isin 更准确
    target_codes = df_ref[COL.CODE]
    df_target = df_today[df_today[COL.CODE].isin(target_codes)].copy()
    
    # 合并昨日收盘价基准 (因为 df_today 里的 '昨收盘' 可能不准，或者直接用 ref 里的更安全)
    df_target = df_target.merge(df_ref[[COL.CODE, '昨日收盘价_Ref']], on=COL.CODE, how='inner')
    
    # 过滤无效数据
    df_target = df_target[(df_target[COL.STD_AMOUNT] > 0) & (df_target[COL.OPEN] > 0)]
    
    if df_target.empty:
        return {}
        
    stats = {}
    
    # --- 核心指标 1: 溢价率 (开盘 / 昨收 - 1) ---
    # 适用于：竞价、收盘
    premium = (df_target[COL.OPEN] / df_target['昨日收盘价_Ref']) - 1
    stats[f'{prefix}_{metric_type}溢价'] = round(premium.mean() * 100, 2) # 存百分比
    
    # --- 核心指标 2 & 3: 赚钱效应 & 承接力 (需要当前价) ---
    # 适用于：仅收盘 (竞价时价格=开盘价，无意义)
    if prefix == '收盘' and COL.STD_PRICE in df_target.columns:
        # 赚钱效应 (现价 / 昨收 - 1)
        money_effect = (df_target[COL.STD_PRICE] / df_target['昨日收盘价_Ref']) - 1
        stats[f'{prefix}_{metric_type}赚钱'] = round(money_effect.mean() * 100, 2)
        
        # 日内承接 (现价 / 开盘 - 1)
        support = (df_target[COL.STD_PRICE] / df_target[COL.OPEN]) - 1
        stats[f'{prefix}_{metric_type}承接'] = round(support.mean() * 100, 2)
        
    return stats

# ==================== 1. 核心计算引擎 (Vectorized Engine) ====================

def _calc_daily_sentiment(df: pd.DataFrame, prefix: str) -> Dict[str, float]:
    """
    【核心引擎】基于 Numpy 的全向量化情绪计算 - 优化版
    """
    if df.empty:
        return {}

    amt_col = COL.STD_AMOUNT
    price_col = COL.STD_PRICE
    
    required_cols = [amt_col, price_col, COL.PCT_CHG]
    if not all(c in df.columns for c in required_cols):
        return {}
        
    codes = df[COL.CODE].values.astype(str)
    names = df[COL.NAME].values.astype(str)
    amts = df[amt_col].values
    prices = df[price_col].values
    chgs = df[COL.PCT_CHG].values
    
    limit_ups = df[COL.LIMIT_UP_PRICE].values if COL.LIMIT_UP_PRICE in df.columns else prices * 1.1
    limit_downs = df[COL.LIMIT_DOWN_PRICE].values if COL.LIMIT_DOWN_PRICE in df.columns else prices * 0.9

    names_lower = np.char.lower(names)
    mask_not_st = np.char.find(names_lower, 'st') == -1
    
    mask_sh = np.char.startswith(codes, 'sh')
    mask_sz = np.char.startswith(codes, 'sz')
    mask_cyb = np.char.startswith(codes, 'sz3')
    
    m_valid = mask_not_st
    
    is_lu = calculate_limit_up_numpy(prices, limit_ups)
    is_ld = (np.abs(prices - limit_downs) < 0.01) & (chgs < -9.0) & (limit_downs > 0)

    total_amt = np.sum(amts) / 1e8
    sh_amt = np.sum(amts[mask_sh]) / 1e8
    cyb_amt = np.sum(amts[mask_cyb]) / 1e8

    if len(amts) > 15:
        top15_amts = np.partition(amts, -15)[-15:]
        top15_total = np.sum(top15_amts) / 1e8
    else:
        top15_total = total_amt
    
    top15_ratio = (top15_total / total_amt * 100) if total_amt > 0 else 0

    chgs_valid = chgs[m_valid]
    
    count_strong = np.sum(chgs_valid >= 7.0)
    count_weak = np.sum(chgs_valid <= -7.0)
    count_limit_up = np.sum(is_lu & m_valid)
    count_limit_down = np.sum(is_ld & m_valid)
    count_up = np.sum(chgs_valid > 0)
    count_down = np.sum(chgs_valid < 0)

    sh_chgs = chgs[mask_sh]
    cyb_chgs = chgs[mask_cyb]
    
    sh_up = np.sum(sh_chgs > 0)
    sh_down = np.sum(sh_chgs < 0)
    sh_ratio = sh_up / sh_down if sh_down > 0 else float('inf')
    
    cyb_up = np.sum(cyb_chgs > 0)
    cyb_down = np.sum(cyb_chgs < 0)
    cyb_ratio = cyb_up / cyb_down if cyb_down > 0 else float('inf')

    total_ratio = count_up / count_down if count_down > 0 else float('inf')

    return {
        f'{prefix}_总额': round(total_amt, 2),
        f'{prefix}_上海额': round(sh_amt, 2),
        f'{prefix}_创业额': round(cyb_amt, 2),
        f'{prefix}_涨停': int(count_limit_up),
        f'{prefix}_跌停': int(count_limit_down),
        f'{prefix}_强力': int(count_strong),
        f'{prefix}_极弱': int(count_weak),
        f'{prefix}_上涨': int(count_up),
        f'{prefix}_下跌': int(count_down),
        f'{prefix}_全场涨跌比': round(total_ratio, 2) if total_ratio != float('inf') else 99.99,
        f'{prefix}_上海涨跌比': round(sh_ratio, 2) if sh_ratio != float('inf') else 99.99,
        f'{prefix}_创业涨跌比': round(cyb_ratio, 2) if cyb_ratio != float('inf') else 99.99,
        f'{prefix}_前15占比': round(top15_ratio, 2),
    }


def _get_index_data(date_obj: datetime, prefix: str) -> Dict[str, float]:
    """读取指数数据"""
    date_str = date_obj.strftime('%Y-%m-%d')
    file_path = DATA_DIR / f"{date_str}_{prefix}指数.csv"
    
    res = {
        f'{prefix}_上证涨跌幅': 0.0,
        f'{prefix}_深证涨跌幅': 0.0,
        f'{prefix}_创业涨跌幅': 0.0
    }
    
    if not file_path.exists():
        return res
    
    cache_key = f"{date_str}_{prefix}_index"
    if cache_key in _MARKET_MASKS_CACHE:
        return _MARKET_MASKS_CACHE[cache_key]
    
    try:
        df_raw = pd.read_csv(file_path, encoding='gbk')
    except:
        try:
            df_raw = pd.read_csv(file_path, encoding='utf-8-sig')
        except:
            return res
    
    if df_raw.empty:
        return res
    
    df_raw['code'] = df_raw['code'].astype(str).str.strip().str.lower()
    pct_col = '涨跌(%)' if '涨跌(%)' in df_raw.columns else '涨跌幅'
    
    lookup = dict(zip(df_raw['code'], df_raw[pct_col]))
    
    res[f'{prefix}_上证涨跌幅'] = float(lookup.get('sh000001', 0.0))
    res[f'{prefix}_深证涨跌幅'] = float(lookup.get('sz399001', 0.0))
    res[f'{prefix}_创业涨跌幅'] = float(lookup.get('sz399006', 0.0))
    
    _MARKET_MASKS_CACHE[cache_key] = res
    return res


# ==================== 2. 数据处理流 (Pipeline) ====================

def process_single_date(target_date: datetime) -> Optional[Dict]:
    """
    处理单日的所有数据 (竞价 + 收盘 + 指数 + 【新增】养家心法指标)
    
    """
    date_str = target_date.strftime('%Y-%m-%d')
    combined_data = {'日期': date_str, '_raw_date': target_date}
    
    # 1. 获取基础数据
    df_jj = read_market_data(target_date, '竞价行情')
    df_close = read_market_data(target_date, '收盘行情')
    
    has_data = False
    
    # 2. 获取昨日 Top 榜单 (用于计算养家心法指标)
    # 只有当今天有数据时，才去读昨天的，节省IO
    df_top15_amt_ref = None
    df_top20_ret_ref = None
    if not df_jj.empty or not df_close.empty:
        df_top15_amt_ref, df_top20_ret_ref = _get_yesterday_top_lists(target_date)

    # 3. 处理竞价数据
    if not df_jj.empty:
        has_data = True
        # 基础统计
        stats_jj = _calc_daily_sentiment(df_jj, prefix='竞价')
        combined_data.update(stats_jj)
        # 指数
        idx_jj = _get_index_data(target_date, '竞价')
        combined_data.update(idx_jj)
        
        # 【新增】养家心法 - 竞价 (只看溢价)
        if df_top15_amt_ref is not None:
            # 这里的 '核心' 对应成交额前15，'妖股' 对应涨幅前20，可根据习惯修改 key
            combined_data.update(_calc_yangjia_metrics(df_jj, df_top15_amt_ref, '竞价', '核心')) 
            combined_data.update(_calc_yangjia_metrics(df_jj, df_top20_ret_ref, '竞价', '妖股'))

    # 4. 处理收盘数据
    if not df_close.empty:
        has_data = True
        # 基础统计
        stats_close = _calc_daily_sentiment(df_close, prefix='收盘')
        combined_data.update(stats_close)
        # 指数
        idx_close = _get_index_data(target_date, '收盘')
        combined_data.update(idx_close)
        
        # 【新增】养家心法 - 收盘 (溢价、赚钱、承接)
        if df_top15_amt_ref is not None:
            combined_data.update(_calc_yangjia_metrics(df_close, df_top15_amt_ref, '收盘', '核心'))
            combined_data.update(_calc_yangjia_metrics(df_close, df_top20_ret_ref, '收盘', '妖股'))
            
    if has_data:
        return combined_data
    
    return None


def calculate_derivatives(df: pd.DataFrame) -> pd.DataFrame:
    """
    【向量化】计算衍生指标 (环比增减、涨跌比)
    """
    if df.empty:
        return df
        
    # 确保按日期排序
    if '_raw_date' in df.columns:
        df = df.sort_values('_raw_date')
    
    all_columns = set(df.columns)
    
    for p in ['竞价', '收盘']:
        total_col = f'{p}_总额'
        if total_col not in all_columns:
            continue
            
        # 1. 资金维度
        total_values = df[total_col].values
        
        # 差值
        diff_values = np.zeros_like(total_values)
        diff_values[1:] = np.diff(total_values)
        df[f'{p}_资金增减'] = diff_values
        
        # 增减幅
        pct_values = np.zeros_like(total_values, dtype=float)
        # 避免除以0警告
        valid_mask = total_values[:-1] != 0
        pct_values[1:][valid_mask] = np.diff(total_values)[valid_mask] / total_values[:-1][valid_mask]
        df[f'{p}_增减幅'] = pct_values
        
        # 2. 结构维度
        for sub in ['上海额', '创业额', '涨停', '跌停', '强力', '极弱']:
            col_name = f'{p}_{sub}'
            if col_name in all_columns:
                sub_values = df[col_name].values
                diff_sub = np.zeros_like(sub_values)
                diff_sub[1:] = np.diff(sub_values)
                # 使用 float 类型，避免 int 溢出（NaN/inf 会变成 -2147483648）
                df[f'{p}_{sub}_diff'] = diff_sub
        
        # 3. 涨跌比
        up_col = f'{p}_上涨'
        down_col = f'{p}_下跌'
        if up_col in all_columns and down_col in all_columns:
            up_values = df[up_col].values
            down_values = df[down_col].values
            
            # 防止除以 0
            down_safe = np.where(down_values == 0, 1, down_values)
            ratio_values = up_values / down_safe
            df[f'{p}_全场涨跌比'] = np.round(ratio_values, 2)
        
    return df


# ==================== 3. 主入口 (Main API) ====================

def get_sentiment_trend_report(date_list: List[datetime]) -> pd.DataFrame:
    """
    获取情绪趋势报告 (自动增量更新，带磁盘缓存)
    """
    old_df = pd.DataFrame()
    if SENTIMENT_TREND_PATH.exists():
        try:
            old_df = pd.read_csv(SENTIMENT_TREND_PATH, dtype={'日期': str})
            if '日期' in old_df.columns:
                old_df['_raw_date'] = pd.to_datetime(old_df['日期'])
        except Exception:
            old_df = pd.DataFrame()

    processed_dates = set()
    if not old_df.empty and '日期' in old_df.columns:
        processed_dates = set(old_df['日期'].dropna().astype(str).tolist())
    
    needed_dates = []
    date_strs = [d.strftime('%Y-%m-%d') for d in date_list]
    
    # 检查新增日期
    for d, d_str in zip(date_list, date_strs):
        if d_str not in processed_dates:
            needed_dates.append(d)
        else:
            # 简单的完整性检查：如果缓存里没有新加的指标（比如核心溢价），也重算
            cached_rows = old_df[old_df['日期'] == d_str]
            if not cached_rows.empty:
                # 检查是否包含关键的新指标列，如果没有，说明是旧缓存，需要更新
                if '收盘_核心赚钱' not in cached_rows.columns: 
                    needed_dates.append(d)
                else:
                    # 检查数据是否有效
                    vals = cached_rows.iloc[0].values
                    if np.any(pd.isna(vals)):
                        needed_dates.append(d)
            
    new_rows = []
    if needed_dates:
        # 去重
        needed_dates = sorted(list(set(needed_dates)))
        print(f"📊 增量计算 {len(needed_dates)} 个日期的情绪数据 (含养家心法)...")
        
        for d in needed_dates:
            row = process_single_date(d)
            if row:
                new_rows.append(row)
                
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        if not old_df.empty:
            # 如果是重算已有日期，先删除旧记录
            new_date_strs = set(new_df['日期'].values)
            old_df = old_df[~old_df['日期'].isin(new_date_strs)]
            combined_df = pd.concat([old_df, new_df], ignore_index=True, copy=False)
        else:
            combined_df = new_df
            
        combined_df = combined_df[combined_df['日期'].notna() & (combined_df['日期'] != '')]
        combined_df = combined_df.sort_values('_raw_date').drop_duplicates(subset=['日期'], keep='last')
        
        final_df = calculate_derivatives(combined_df)
        
        MARKET_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        # 保存所有列（除了临时列）
        save_cols = [c for c in final_df.columns if c != '_raw_date']
        
        # 排除不需要的旧列名
        exclude_cols = ['竞价成交额', '收盘成交额', '竞价平均涨跌幅', '收盘平均涨跌幅', '上涨家数', '下跌家数', '平盘家数']
        used_cols = [col for col in save_cols if col not in exclude_cols]
        
        final_df[used_cols].to_csv(SENTIMENT_TREND_PATH, index=False, encoding='utf-8-sig', float_format='%.2f')
        
        print(f"✅ 缓存已更新，包含 Top15/Top20 情绪指标")
    else:
        final_df = old_df
        if not final_df.empty:
            print("📋 使用缓存数据")
    
    if not final_df.empty:
        requested_dates = set(date_strs)
        filtered_df = final_df[final_df['日期'].isin(requested_dates)].copy()
        if not filtered_df.empty:
            return calculate_derivatives(filtered_df)
    
    return pd.DataFrame()


# ==================== 4. 单日情绪分析 (兼容旧接口) ====================

def analyze_single_day(trade_date: datetime) -> Dict[str, any]:
    """
    分析单日市场情绪 (兼容旧接口)
    """
    result = process_single_date(trade_date)
    if result is None:
        return {
            'date': trade_date.strftime('%Y-%m-%d'),
            'auction': {},
            'close': {}
        }
    
    return {
        'date': result['日期'],
        'auction': {k: v for k, v in result.items() if k.startswith('竞价_')},
        'close': {k: v for k, v in result.items() if k.startswith('收盘_')}
    }