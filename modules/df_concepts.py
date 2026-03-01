# -*- coding: utf-8 -*-
"""
题材分析模块

提供题材维度的统计分析功能，包括：
- 资金增量计算
- 题材聚合统计
- 涨跌停统计（竞价显示涨停股票，收盘显示连板股票）
- 增量先锋识别
- 双涨幅标签展示
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Tuple, List, Dict

from tools.config import COL, BLACKLIST, HOT_KEYWORDS
from tools.data_loader import read_market_data, load_concept_data, get_trade_dates
from tools.utils import ensure_numeric_columns, add_hot_keywords_vectorized, calculate_limit_up_numpy
from modules.analyzer_tags import build_merged_tags, build_close_tags, build_auction_tags


# =============================================================================
# 日期工具函数
# =============================================================================

def _get_prev_date(target_date: datetime) -> datetime:
    """获取前一个交易日"""
    all_dates = get_trade_dates(count=30)
    
    try:
        target_dt = target_date if isinstance(target_date, datetime) else datetime.combine(target_date, datetime.min.time())
        curr_idx = all_dates.index(target_dt)
        prev_date = all_dates[curr_idx - 1] if curr_idx > 0 else all_dates[0]
        return prev_date
    except ValueError:
        return all_dates[-2] if len(all_dates) >= 2 else all_dates[-1]


# =============================================================================
# 资金计算函数
# =============================================================================

def _calculate_increment(
    df_today: pd.DataFrame, 
    df_yest: pd.DataFrame, 
    amt_col: str
) -> pd.DataFrame:
    """
    【向量化】计算资金增量
    
    计算逻辑: 增量 = 今日金额 - 昨日金额
    """
    t = df_today[[COL.CODE, amt_col]].copy()
    y = df_yest[[COL.CODE, amt_col]].rename(columns={amt_col: f'{amt_col}_昨'})
    
    merged = t.merge(y, on=COL.CODE, how='left')
    merged[f'{amt_col}_昨'] = merged[f'{amt_col}_昨'].fillna(0)
    merged[COL.INCREMENT_BILLION] = (merged[amt_col] - merged[f'{amt_col}_昨']) / 1e8
    
    return merged[[COL.CODE, COL.INCREMENT_BILLION]]


# =============================================================================
# 概念标签处理函数
# =============================================================================

def _prepare_concept_tags(df_stocks: pd.DataFrame) -> pd.DataFrame:
    """
    准备概念标签（概念+行业）
    
    将所属概念和所属行业合并，并拆分为列表格式
    """
    concept_series = df_stocks[COL.CONCEPT].fillna('') if COL.CONCEPT in df_stocks.columns else pd.Series([''] * len(df_stocks))
    industry_series = df_stocks[COL.INDUSTRY].fillna('') if COL.INDUSTRY in df_stocks.columns else pd.Series([''] * len(df_stocks))
    
    df_stocks['tags'] = (concept_series + ';' + industry_series).str.split(';')
    
    return df_stocks


# =============================================================================
# 统计计算函数
# =============================================================================

def _calculate_concept_stats(df_valid: pd.DataFrame) -> pd.DataFrame:
    """
    计算题材基础统计数据
    
    聚合指标: 家数、资金增量、平均涨跌、总成交额、红盘率
    """
    amount_col = COL.STD_AMOUNT
    agg_rules = {
        COL.CODE: 'count',
        COL.INCREMENT_BILLION: 'sum',
        COL.PCT_CHG: 'mean',
        amount_col: lambda x: x.sum() / 1e8
    }
    
    df_valid['is_red'] = df_valid[COL.PCT_CHG] > 0
    
    grp = df_valid.groupby('tags')
    stats = grp.agg(agg_rules).rename(columns={
        COL.CODE: COL.STOCK_COUNT,
        COL.PCT_CHG: COL.AVG_CHANGE_PCT,
        amount_col: COL.TOTAL_AMOUNT_BILLION
    })
    
    stats[COL.RED_RATIO_PCT] = (grp['is_red'].mean() * 100).round(1)

    return stats


def _calculate_concept_limit_stats(df_exploded: pd.DataFrame, data_type: str = '收盘') -> pd.DataFrame:
    """
    计算题材维度的涨跌停统计
    
    统计指标: 涨停数、跌停数、连板数、首板数、大涨数、大跌数、炸板数、涨停/连板股票
    
    参数:
        df_exploded: 炸开概念标签后的数据
        data_type: '竞价' 或 '收盘'，决定股票列表列名
    
    返回:
        DataFrame 包含各题材的涨跌停统计
    """
    if df_exploded.empty:
        return pd.DataFrame()

    # 1. 聚合统计各指标
    agg_dict = {
        'is_limit_up': 'sum',
        'is_limit_down': 'sum',
        'is_lianban': 'sum',
        'is_shouban': 'sum',
        'is_big_up': 'sum',
        'is_big_down': 'sum',
        'is_zhaban': 'sum',
        '股票代码': 'count'
    }

    for col in agg_dict.keys():
        if col not in df_exploded.columns:
            df_exploded[col] = False if col != '股票代码' else df_exploded['股票代码']

    stats = df_exploded.groupby('tags').agg(agg_dict).reset_index()

    # 2. 重命名列
    stats = stats.rename(columns={
        'tags': '题材名称',
        '股票代码': '家数',
        'is_limit_up': '涨停数',
        'is_limit_down': '跌停数',
        'is_lianban': '连板数',
        'is_shouban': '首板数',
        'is_big_up': '大涨数',
        'is_big_down': '大跌数',
        'is_zhaban': '炸板数'
    })

    # 3. 转换为整数
    numeric_cols = ['家数', '涨停数', '跌停数', '连板数', '首板数', '大涨数', '大跌数', '炸板数']
    for col in numeric_cols:
        stats[col] = pd.to_numeric(stats[col], errors='coerce').fillna(0).astype(int)

    # 4. 计算比率（相对于家数）
    stats['涨停率%'] = (stats['涨停数'] / stats['家数'] * 100).round(2)
    stats['跌停率%'] = (stats['跌停数'] / stats['家数'] * 100).round(2)
    stats['大涨率%'] = (stats['大涨数'] / stats['家数'] * 100).round(2)
    stats['大跌率%'] = (stats['大跌数'] / stats['家数'] * 100).round(2)

    # 5. 获取涨停/连板股票列表
    name_col = '股票简称' if '股票简称' in df_exploded.columns else COL.NAME
    if name_col in df_exploded.columns:
        # 根据数据类型确定显示内容：竞价显示涨停股，收盘显示连板股
        if data_type == '竞价':
            status_df = df_exploded[df_exploded['is_limit_up'] == True]
            stock_col_name = '涨停股票'
        else:
            status_df = df_exploded[df_exploded['is_lianban'] == True]
            stock_col_name = '连板股票'
        
        if not status_df.empty:
            stocks_list = []
            for tag, group in status_df.groupby('tags'):
                stock_names = ','.join(group[name_col].unique()) if not group.empty else ''
                stocks_list.append({'题材名称': tag, stock_col_name: stock_names})
            if stocks_list:
                stocks_df = pd.DataFrame(stocks_list)
                stats = stats.merge(stocks_df, on='题材名称', how='left')
    
    # 6. 确保股票列存在
    stock_col = '涨停股票' if data_type == '竞价' else '连板股票'
    if stock_col not in stats.columns:
        stats[stock_col] = ''
    stats[stock_col] = stats[stock_col].fillna('')

    return stats


# =============================================================================
# 增量先锋函数
# =============================================================================

def _find_increment_leaders(df_valid: pd.DataFrame, target_date: datetime, prev_date: datetime) -> pd.DataFrame:
    """
    寻找每个题材的"增量先锋"
    
    增量先锋定义: 每个题材内资金增量最大的股票
    """
    df_valid_sorted = df_valid.sort_values(COL.INCREMENT_BILLION, ascending=False)
    leaders = df_valid_sorted.drop_duplicates(subset=['tags'], keep='first').copy()
    
    try:
        df_merged_tags = build_merged_tags(target_date, prev_date)
        if not df_merged_tags.empty:
            leaders = leaders.merge(
                df_merged_tags[[COL.CODE, '合并标签', '竞价涨幅', '收盘涨幅']], 
                on=COL.CODE, 
                how='left'
            )
    except Exception as e:
        print(f"获取合并标签出错: {e}")
    
    leaders['合并标签'] = leaders.get('合并标签', '--').fillna('--')
    leaders['竞价涨幅'] = leaders.get('竞价涨幅', None)
    leaders['收盘涨幅'] = leaders.get('收盘涨幅', None)
    
    def format_pct(pct):
        return f"{pct:.1f}%" if pd.notna(pct) else '--'
    
    leaders['增量先锋'] = (
        leaders[COL.NAME] + "(" +
        leaders['竞价涨幅'].apply(format_pct) + "/" +
        leaders['收盘涨幅'].apply(format_pct) + ") " +
        "[" + leaders['合并标签'] + "] " +
        "[" + leaders[COL.CODE] + "]"
    )
    
    return leaders


def _merge_leader_to_stats(stats: pd.DataFrame, leaders: pd.DataFrame) -> pd.DataFrame:
    """将增量先锋信息合并到题材统计表"""
    stats = stats.reset_index().rename(columns={'tags': COL.CONCEPT_NAME})
    stats = stats.merge(
        leaders[['tags', '增量先锋', COL.CODE]], 
        left_on=COL.CONCEPT_NAME, 
        right_on='tags', 
        how='left'
    )
    
    stats = stats.drop(columns=['tags'])
    stats[COL.LEADER_CODE] = stats[COL.CODE]
    stats = stats.drop(columns=[COL.CODE])
    stats = stats.rename(columns={'增量先锋': COL.INCREMENT_LEADER})
    
    return stats.sort_values(COL.INCREMENT_BILLION, ascending=False)


# =============================================================================
# 主函数
# =============================================================================

def get_concepts_data(
    target_date: datetime, 
    data_type: str = '竞价'
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    获取题材分析数据
    
    主要功能:
        1. 读取今日和昨日行情数据
        2. 计算个股资金增量
        3. 聚合计算题材统计指标（基础统计 + 涨跌停统计）
        4. 识别每个题材的增量先锋
        5. 获取双涨幅标签信息
    
    参数:
        target_date: 目标日期
        data_type: 数据类型，'竞价' 或 '收盘'
    
    返回:
        Tuple[concept_stats, stock_details]:
            - concept_stats: 题材维度的统计表
            - stock_details: 个股维度的详情表
    """
    # 1. 确定数据源
    file_type = "竞价行情" if data_type == '竞价' else "收盘行情"
    
    # 2. 读取今日数据
    df_today = read_market_data(target_date, file_type)
    if df_today.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    # 3. 获取前一交易日
    prev_date_dt = _get_prev_date(target_date)
    
    # 4. 读取昨日数据
    df_yest = read_market_data(prev_date_dt, file_type)
    
    # 5. 检查必要列
    target_amt_col = COL.STD_AMOUNT
    if target_amt_col not in df_today.columns:
        return pd.DataFrame(), pd.DataFrame()
    
    # 6. 计算个股资金增量
    if not df_yest.empty:
        df_inc = _calculate_increment(df_today, df_yest, target_amt_col)
        df_today = df_today.merge(df_inc, on=COL.CODE, how='left')
    else:
        df_today[COL.INCREMENT_BILLION] = 0.0
    
    # 7. 加载概念数据
    df_concepts_map = load_concept_data(target_date)
    if df_concepts_map.empty:
        return pd.DataFrame(), df_today
    
    # 8. 合并个股与概念
    df_stocks = df_today.merge(df_concepts_map, on=COL.CODE, how='left')
    
    # 9. 准备概念标签
    df_stocks = _prepare_concept_tags(df_stocks)
    
    # 10. 炸开概念标签
    df_exploded = df_stocks.explode('tags')
    df_valid = df_exploded[df_exploded['tags'].notna() & (df_exploded['tags'] != '')].copy()

    if df_valid.empty:
        return pd.DataFrame(), df_stocks

    # 11. 获取个股涨跌停状态并合并
    try:
        # 统一从 analyzer_tags 获取状态标记，避免重复计算
        if data_type == '竞价':
            df_tags_stats = build_auction_tags(target_date, prev_date_dt)
        else:
            df_tags_stats = build_close_tags(target_date, prev_date_dt)
        
        if not df_tags_stats.empty:
            df_valid = df_valid.merge(
                df_tags_stats[['股票代码', 'is_limit_up', 'is_limit_down', 'is_lianban',
                              'is_shouban', 'is_big_up', 'is_big_down', 'is_zhaban']],
                left_on=COL.CODE,
                right_on='股票代码',
                how='left'
            )
    except Exception as e:
        print(f"获取涨跌停状态出错: {e}")

    # 12. 计算题材基础统计
    stats = _calculate_concept_stats(df_valid)

    # 13. 计算题材涨跌停统计并合并
    try:
        df_limit_stats = _calculate_concept_limit_stats(df_valid, data_type=data_type)
        if not df_limit_stats.empty:
            stats = stats.reset_index().rename(columns={'tags': '题材名称'})
            
            # 根据数据类型确定股票列名
            stock_col = '涨停股票' if data_type == '竞价' else '连板股票'
            merge_cols = ['题材名称', '涨停数', '跌停数', '连板数', '首板数',
                         '大涨数', '大跌数', '炸板数', '涨停率%', '跌停率%',
                         '大涨率%', '大跌率%', stock_col]
            
            # 只合并存在的列
            available_cols = [c for c in merge_cols if c in df_limit_stats.columns]
            stats = stats.merge(
                df_limit_stats[available_cols],
                on='题材名称',
                how='left'
            )
            
            # 填充缺失值
            for col in ['涨停数', '跌停数', '连板数', '首板数', '大涨数', '大跌数', '炸板数']:
                if col in stats.columns:
                    stats[col] = stats[col].fillna(0).astype(int)
            for col in ['涨停率%', '跌停率%', '大涨率%', '大跌率%']:
                if col in stats.columns:
                    stats[col] = stats[col].fillna(0.0)
            if stock_col in stats.columns:
                stats[stock_col] = stats[stock_col].fillna('')
    except Exception as e:
        print(f"计算题材涨跌停统计出错: {e}")

    # 14. 寻找增量先锋
    leaders = _find_increment_leaders(df_valid, target_date, prev_date_dt)

    # 15. 合并结果
    stats_final = _merge_leader_to_stats(stats, leaders)

    # 16. 格式化比率列为2位小数字符串（确保CSV显示正确）
    for col in ['涨停率%', '跌停率%', '大涨率%', '大跌率%']:
        if col in stats_final.columns:
            stats_final[col] = stats_final[col].apply(lambda x: f"{x:.2f}")

    # 16.5 合并标签到个股数据
    try:
        df_merged_tags = build_merged_tags(target_date, prev_date_dt)
        if not df_merged_tags.empty:
            df_stocks = df_stocks.merge(
                df_merged_tags[['股票代码', '合并标签']], 
                left_on=COL.CODE, 
                right_on='股票代码', 
                how='left'
            )
            df_stocks['合并标签'] = df_stocks['合并标签'].fillna('--')
    except Exception as e:
        print(f"获取合并标签出错: {e}")

    # 17. 精简 stock_details 列 - 只保留UI下钻需要的列
    # 需要的列：股票代码、股票名称、涨跌幅、成交额、增量(亿)、tags、合并标签
    essential_cols = [
        COL.CODE,      # 股票代码
        COL.NAME,      # 股票名称
        COL.PCT_CHG,   # 涨跌幅
        COL.STD_AMOUNT,# 成交额
        COL.INCREMENT_BILLION,  # 增量(亿)
        'tags',        # 包含现价、所属行业、所属概念等信息的标签
        '合并标签'      # 竞价标签.收盘标签
    ]
    # 只保留存在的列
    available_essential_cols = [c for c in essential_cols if c in df_stocks.columns]
    df_stocks_minimal = df_stocks[available_essential_cols].copy()

    # 注意：保存逻辑由 service_layer.py 统一处理
    # 业务模块只负责计算，不直接保存

    return stats_final, df_stocks_minimal
