# -*- coding: utf-8 -*-
"""
增量计算 Top15 股票数据
支持增量更新，计算股票的出现次数和连续天数
"""

import sys
import os
import pandas as pd
import warnings
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.data_loader import get_trade_dates, read_market_data
from tools.config import TOP15_CACHE_PATH, DATA_DIR


def get_raw_data_dates():
    """
    获取原始数据目录中所有可用的日期
    
    Returns:
        list: 排序后的日期字符串列表 (格式: YYYY-MM-DD)
    """
    # 同时检查竞价行情和收盘行情文件，只要有一个存在就认为该日期有效
    dates = set()
    for file_path in DATA_DIR.glob('*_竞价行情.csv'):
        dates.add(file_path.stem.split('_')[0])
    for file_path in DATA_DIR.glob('*_收盘行情.csv'):
        dates.add(file_path.stem.split('_')[0])
    return sorted(list(dates))


def read_historical_data():
    """
    读取已保存的历史 Top15 数据
    
    Returns:
        pd.DataFrame: 历史数据，包含日期、类型、股票代码等信息
    """
    try:
        if not TOP15_CACHE_PATH.exists() or TOP15_CACHE_PATH.stat().st_size == 0:
            return pd.DataFrame()
        
        # 先尝试读取第一行判断是否有表头
        with open(TOP15_CACHE_PATH, 'r', encoding='utf-8-sig') as f:
            first_line = f.readline().strip()
        
        # 如果第一行包含"日期"字样，说明有表头
        if '日期' in first_line:
            df = pd.read_csv(TOP15_CACHE_PATH, dtype={'股票代码': str})
        else:
            # 没有表头，使用自定义列名
            columns = ['日期', '类型', '股票代码', '股票简称', '金额', '涨跌幅', '出现次数', '连续天数']
            df = pd.read_csv(TOP15_CACHE_PATH, header=None, names=columns, dtype={'股票代码': str})
        
        df['日期'] = pd.to_datetime(df['日期'])
        return df
    except Exception as e:
        print(f"⚠️ 读取历史数据失败: {e}")
        return pd.DataFrame()


def find_missing_dates(df_hist, raw_dates, force_dates=None):
    """
    找出缺失的日期
    
    Args:
        df_hist: 历史数据 DataFrame
        raw_dates: 原始数据日期列表
        force_dates: 强制重新计算的日期列表
    
    Returns:
        list: 缺失的日期列表
    """
    hist_dates = set(df_hist['日期'].dt.strftime('%Y-%m-%d')) if not df_hist.empty else set()
    missing = set([d for d in raw_dates if d not in hist_dates])
    
    if force_dates:
        missing.update(force_dates)
    
    return sorted(missing)


def find_missing_by_type(df_hist, raw_dates):
    """
    分别找出竞价和收盘的缺失日期
    
    Args:
        df_hist: 历史数据 DataFrame
        raw_dates: 原始数据日期列表
    
    Returns:
        tuple: (竞价缺失日期列表, 收盘缺失日期列表)
    """
    missing_auction = set()
    missing_close = set()
    
    if df_hist.empty or '日期' not in df_hist.columns or '类型' not in df_hist.columns:
        return sorted(raw_dates), sorted(raw_dates)
    
    # 确保历史数据的日期列是字符串格式，方便比较
    df_hist_copy = df_hist.copy()
    if pd.api.types.is_datetime64_any_dtype(df_hist_copy['日期']):
        df_hist_copy['日期'] = df_hist_copy['日期'].dt.strftime('%Y-%m-%d')
    
    for date_str in raw_dates:
        # 使用字符串比较，避免 datetime 精度问题
        df_date = df_hist_copy[df_hist_copy['日期'] == date_str]
        
        if '类型' in df_date.columns:
            if '竞价' not in df_date['类型'].values:
                missing_auction.add(date_str)
            if '收盘' not in df_date['类型'].values:
                missing_close.add(date_str)
        else:
            missing_auction.add(date_str)
            missing_close.add(date_str)
    
    return sorted(missing_auction), sorted(missing_close)


def calculate_top15_for_date(date_str):
    """
    计算指定日期的 Top15 股票数据（竞价和收盘）
    
    Args:
        date_str: 日期字符串 (格式: YYYY-MM-DD)
    
    Returns:
        pd.DataFrame: 包含日期、类型、股票代码、股票简称、金额、涨跌幅的 DataFrame
    """
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    results = []
    
    for data_type, type_name in [('竞价行情', '竞价'), ('收盘行情', '收盘')]:
        # 检查原始数据文件是否存在且不为空
        file_path = DATA_DIR / f"{date_str}_{data_type}.csv"
        if not file_path.exists():
            print(f"⚠️ {date_str} {data_type} 数据文件不存在")
            continue
        
        if file_path.stat().st_size == 0:
            print(f"⚠️ {date_str} {data_type} 数据文件为空")
            continue
        
        # 读取数据
        df_raw = read_market_data(date_obj, data_type)
        
        # 验证数据完整性
        if df_raw.empty:
            print(f"⚠️ {date_str} {data_type} 数据读取为空")
            continue
        
        if '金额' not in df_raw.columns:
            print(f"⚠️ {date_str} {data_type} 数据缺少 '金额' 列")
            continue
        
        if df_raw['金额'].isna().all():
            print(f"⚠️ {date_str} {data_type} 数据 '金额' 列全部为空")
            continue
        
        # 计算 Top15
        df_top15 = df_raw.nlargest(15, '金额').copy()
        
        # 验证计算结果
        if df_top15.empty:
            print(f"⚠️ {date_str} {data_type} 计算 Top15 结果为空")
            continue
        
        # 处理数据格式
        df_top15['日期'] = pd.to_datetime(date_str)
        df_top15['类型'] = type_name
        
        # 确保必要列存在
        columns_to_keep = ['日期', '类型', '股票代码', '股票简称', '金额', '涨跌幅']
        existing_columns = [col for col in columns_to_keep if col in df_top15.columns]
        
        if len(existing_columns) < 4:  # 至少需要日期、类型、股票代码、金额
            print(f"⚠️ {date_str} {data_type} 数据缺少必要列")
            continue
        
        df_top15 = df_top15[existing_columns]
        results.append(df_top15)
    
    if not results:
        print(f"⚠️ {date_str} 没有有效的 Top15 数据")
        return None
    
    return pd.concat(results, ignore_index=True)


def calculate_streak_v2(stock_dates_set, current_date_str, trade_date_strs):
    """
    计算股票连续上榜天数（向量化实现）
    
    Args:
        stock_dates_set: 股票上榜日期集合（不包含当前日期）
        current_date_str: 当前日期字符串
        trade_date_strs: 交易日序列列表
    
    Returns:
        int: 连续上榜天数
    """
    try:
        start_idx = trade_date_strs.index(current_date_str)
    except ValueError:
        return 0
    
    streak = 1  # 当前日期算1天
    for i in range(start_idx - 1, -1, -1):
        if trade_date_strs[i] in stock_dates_set:
            streak += 1
        else:
            break
    return streak


def calculate_statistics(df_new, df_current, date_str, trade_dates_all):
    """
    计算新增数据的统计信息（出现次数和连续天数）
    
    Args:
        df_new: 新增数据 DataFrame
        df_current: 当前历史数据 DataFrame
        date_str: 当前日期字符串
        trade_dates_all: 交易日序列列表
    
    Returns:
        pd.DataFrame: 添加了统计信息的 DataFrame
    """
    df_new['出现次数'] = 0
    df_new['连续天数'] = 0
    
    if df_current.empty or '类型' not in df_current.columns:
        df_new['出现次数'] = 1
        df_new['连续天数'] = 1
        return df_new
    
    # 排除当前日期的历史数据（避免重复计算）
    current_date = pd.to_datetime(date_str)
    df_hist_filtered = df_current[df_current['日期'] != current_date].copy()
    
    for data_type in ['竞价', '收盘']:
        df_type_new = df_new[df_new['类型'] == data_type].copy()
        df_type_hist = df_hist_filtered[df_hist_filtered['类型'] == data_type].copy()
        
        for idx, row in df_type_new.iterrows():
            code = row['股票代码']
            
            if not df_type_hist.empty:
                total_count = (df_type_hist['股票代码'] == code).sum() + 1
                stock_dates = set(df_type_hist[df_type_hist['股票代码'] == code]['日期'].dt.strftime('%Y-%m-%d'))
                streak = calculate_streak_v2(stock_dates, date_str, trade_dates_all)
            else:
                total_count = 1
                streak = 1
            
            df_new.loc[idx, '出现次数'] = total_count
            df_new.loc[idx, '连续天数'] = streak
    
    return df_new


def display_statistics(df_new):
    """
    展示统计信息
    
    Args:
        df_new: 包含统计信息的 DataFrame
    """
    for data_type in ['竞价', '收盘']:
        df_type_today = df_new[df_new['类型'] == data_type]
        print(f"\n  【{data_type}行情】")
        
        if df_type_today.empty:
            print(f"  Top15数量: 0 条")
            continue

        print(f"  {'股票代码':<12}{'股票简称':<10}{'出现次数':<10}{'连续天数':<10}")
        print("  " + "-" * 42)
        
        for _, row in df_type_today.iterrows():
            print(f"  {row['股票代码']:<12}{row['股票简称']:<10}{row['出现次数']:<10}{row['连续天数']:<10}")


def save_to_file(df_new):
    """
    保存数据到文件（自动去重）
    
    Args:
        df_new: 要保存的 DataFrame
    """
    # 确保列顺序一致
    expected_columns = ['日期', '类型', '股票代码', '股票简称', '金额', '涨跌幅', '出现次数', '连续天数']
    # 只保留存在的列，并按预期顺序排列
    columns_to_save = [col for col in expected_columns if col in df_new.columns]
    df_save = df_new[columns_to_save].copy()
    
    # 统一日期格式为字符串 YYYY-MM-DD
    if '日期' in df_save.columns:
        df_save['日期'] = pd.to_datetime(df_save['日期']).dt.strftime('%Y-%m-%d')
    
    if TOP15_CACHE_PATH.exists() and TOP15_CACHE_PATH.stat().st_size > 0:
        # 读取现有数据，合并后去重
        try:
            df_existing = pd.read_csv(TOP15_CACHE_PATH, dtype={'股票代码': str})
            df_combined = pd.concat([df_existing, df_save], ignore_index=True)
            # 根据日期、类型、股票代码去重，保留最后出现的记录
            df_combined = df_combined.drop_duplicates(subset=['日期', '类型', '股票代码'], keep='last')
            df_combined.to_csv(TOP15_CACHE_PATH, index=False, encoding='utf_8_sig')
        except Exception as e:
            # 如果读取失败，直接追加
            df_save.to_csv(TOP15_CACHE_PATH, mode='a', header=False, index=False, encoding='utf_8_sig')
    else:
        df_save.to_csv(TOP15_CACHE_PATH, header=True, index=False, encoding='utf_8_sig')


def calculate_and_save_top15():
    """
    计算并保存Top15数据（增量计算）
    
    Returns:
        pd.DataFrame: stocks_df 个股明细数据
    """
    raw_dates = get_raw_data_dates()
    df_current = read_historical_data()
    
    missing_auction, missing_close = find_missing_by_type(df_current, raw_dates)
    missing_dates = sorted(set(missing_auction + missing_close))
    
    if not missing_dates:
        print("✅ 没有缺失的日期")
        return df_current
    
    trade_dates_all = [d.strftime('%Y-%m-%d') for d in get_trade_dates(count=500)]
    
    for date_str in missing_dates:
        df_new = calculate_top15_for_date(date_str)
        if df_new is None:
            continue
        
        df_new = calculate_statistics(df_new, df_current, date_str, trade_dates_all)
        save_to_file(df_new)
        
        df_current = pd.concat([df_current, df_new], ignore_index=True)
    
    return df_current


def main():
    """主函数：执行增量计算流程"""
    print("=" * 80)
    print("处理多个缺失日期的增量计算 (优化版)")
    print("=" * 80)
    
    raw_dates = get_raw_data_dates()
    df_current = read_historical_data()
    
    missing_auction, missing_close = find_missing_by_type(df_current, raw_dates)
    missing_dates = sorted(set(missing_auction + missing_close))
    
    if missing_auction:
        print(f"\n❌ 竞价缺失日期: {missing_auction}")
    if missing_close:
        print(f"\n❌ 收盘缺失日期: {missing_close}")
    
    if not missing_dates:
        print("\n✅ 没有缺失的日期")
        return
    
    trade_dates_all = [d.strftime('%Y-%m-%d') for d in get_trade_dates(count=500)]
    
    for i, date_str in enumerate(missing_dates, 1):
        print(f"\n{'=' * 80}\n[{i}/{len(missing_dates)}] 计算日期: {date_str}\n{'=' * 80}")
        
        df_new = calculate_top15_for_date(date_str)
        if df_new is None:
            print(f"  ⚠️ {date_str} 无数据")
            continue
        
        df_new = calculate_statistics(df_new, df_current, date_str, trade_dates_all)
        display_statistics(df_new)
        save_to_file(df_new)
        
        df_current = pd.concat([df_current, df_new], ignore_index=True)
        
        print(f"  ✅ {date_str} 数据已保存")

    print(f"\n{'=' * 80}\n✅ 所有缺失日期计算完成 (逐天保存)\n{'=' * 80}")


if __name__ == '__main__':
    main()
