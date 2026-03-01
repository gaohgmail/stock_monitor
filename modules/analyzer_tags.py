# -*- coding: utf-8 -*-
"""
核心模块：modules/analyzer_tags_zhengli.py
功能：生成个股结构标签（竞价/收盘），支持全向量化计算。
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Tuple, Dict

from tools.config import COL
from tools.utils import calculate_limit_up_numpy
from tools.data_loader import read_market_data, get_lianban_data
from tools.date_utils import ensure_datetime

# ==================== 常量定义 ====================
COL.CONSECUTIVE_LIMIT_UP_DAYS = "连续涨停天数"
COL.STRUCTURE_TAG = "结构标签"

# ==================== 向量化计算辅助函数 ====================

def _get_volume_level_vectorized(ratio: pd.Series, amt: pd.Series) -> pd.Series:
    """
    【向量化】获取量能级别
    优先级：绝对金额判断 > 倍数判断
    """
    conditions = [
        (amt < 1e6),           # 无量 < 100万
        (amt < 4e6),           # 微量 < 400万
        (ratio < 0.85),        # 缩量
        (ratio < 1.3),         # 平量
        (ratio < 2.0),         # 放量
        (ratio < 5.0)          # 倍量
    ]
    choices = ['无量', '微量', '缩量', '平量', '放量', '倍量']
    return pd.Series(np.select(conditions, choices, default='爆量'), index=ratio.index)


def _get_open_type_vectorized(today_price: pd.Series, 
                              yest_close: pd.Series, 
                              yest_high: pd.Series, 
                              yest_low: pd.Series) -> pd.Series:
    """
    【向量化】获取开盘类型（高开/低开/平开）
    """
    # 优先使用昨高昨低判断
    if yest_high is not None and yest_low is not None:
        conditions = [
            today_price > yest_high,
            today_price < yest_low
        ]
    else:
        conditions = [
            today_price > yest_close,
            today_price < yest_close
        ]
    
    choices = ['高开', '低开']
    return pd.Series(np.select(conditions, choices, default='平开'), index=today_price.index)


def _prepare_base_data(df_today: pd.DataFrame, 
                       df_yest: pd.DataFrame, 
                       df_yest_close: pd.DataFrame) -> pd.DataFrame:
    """
    数据清洗与基础特征计算
    """
    amt_col = COL.STD_AMOUNT
    price_col = COL.STD_PRICE

    # 1. 基础合并：今日数据 + 昨日量能（竞价或收盘）
    df = df_today.merge(
        df_yest[[COL.CODE, amt_col]].rename(columns={amt_col: 'amt_prev'}),
        on=COL.CODE, how='left'
    )
    
    # 2. 合并昨日收盘详情（用于形态判断）
    yest_cols = {
        COL.HIGH: 'y_high', 
        COL.STD_PRICE: 'y_price', 
        COL.LOW: 'y_low', 
        COL.LIMIT_UP_PRICE: 'y_limit', 
        COL.PCT_CHG: 'y_pct'
    }
    df = df.merge(
        df_yest_close[[COL.CODE] + list(yest_cols.keys())].rename(columns=yest_cols),
        on=COL.CODE, how='left'
    )

    # 3. 数值清洗与转换
    numeric_cols = ['amt_prev', 'y_high', 'y_price', 'y_low', 'y_limit', 'y_pct']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['amt_now'] = pd.to_numeric(df[amt_col], errors='coerce').fillna(0)
    
    # 修正昨日金额，避免除零错误 (最小100万)
    df['amt_prev'] = df['amt_prev'].where(df['amt_prev'] >= 1e6, 9.9e5)
    
    # 4. 核心指标计算
    df['ratio'] = df['amt_now'] / df['amt_prev']
    df['pct_chg'] = pd.to_numeric(df[COL.PCT_CHG], errors='coerce').fillna(0)
    df['days'] = pd.to_numeric(df.get(COL.CONSECUTIVE_LIMIT_UP_DAYS, 0), errors='coerce').fillna(0).astype(int)
    
    # 5. 形态标记
    # 昨日炸板：昨高>=昨涨停 且 昨收<昨涨停
    df['is_yest_zhaban'] = (df['y_high'] >= df['y_limit']) & (df['y_price'] < df['y_limit']) & (df['y_limit'] > 0)
    df['is_yest_big_down'] = df['y_pct'] <= -5.0
    df['is_yest_big_up'] = df['y_pct'] >= 5.0
    
    # 昨日跌停 (从 df_today 中获取，前提是上游已合并过连板数据中的状态)
    df['is_yest_limit_down'] = (COL.LIMIT_UP_DOWN_STATUS in df.columns) & (df[COL.LIMIT_UP_DOWN_STATUS] == '跌停')

    return df


# ==================== 核心标签生成逻辑 ====================

def _generate_auction_logic(df: pd.DataFrame) -> pd.DataFrame:
    """
    【竞价阶段】标签生成逻辑
    """
    # 1. 计算辅助指标
    open_price = pd.to_numeric(df[COL.STD_PRICE], errors='coerce').fillna(0)
    vol_level = _get_volume_level_vectorized(df['ratio'], df['amt_now'])
    open_type = _get_open_type_vectorized(open_price, df['y_price'], df['y_high'], df['y_low'])
    days_str = df['days'].astype(str)

    # 2. 标签组件构建
    lianban_tags = vol_level + days_str + '板'
    zhaban_tags = '炸板' + open_type + vol_level
    daz_tags = '大涨' + open_type + vol_level
    dad_tags = '大跌' + open_type + vol_level

    # 3. 优先级判断条件 (Priority Queue)
    conditions = [
        (df['pct_chg'] >= 33),                           # 1. 新股
        (df['is_yest_limit_down']),                      # 2. 昨日跌停
        (df['days'] >= 2),                               # 3. 连板
        (df['days'] == 1),                               # 4. 昨日首板
        (df['is_yest_zhaban']),                          # 5. 昨日炸板
        (df['is_yest_big_up']),                          # 6. 昨日大涨
        (df['is_yest_big_down']),                        # 7. 昨日大跌
        (df['ratio'] >= 3.0) & (df['amt_now'] >= 1e6),   # 8. 突发放量
        (df['ratio'] >= 2.0) & (df['amt_now'] >= 1e6)    # 9. 一般放量
    ]

    choices = [
        '新股上市',
        '昨日跌停',
        lianban_tags,
        '昨日首板',
        zhaban_tags,
        daz_tags,
        dad_tags,
        '突发放量',
        '一般放量'
    ]

    df[COL.STRUCTURE_TAG] = np.select(conditions, choices, default='--')
    return df


def _generate_close_logic(df: pd.DataFrame, days_yest: pd.Series = None) -> pd.DataFrame:
    """
    【收盘阶段】标签生成逻辑
    """
    # 1. 计算辅助指标
    vol_level = _get_volume_level_vectorized(df['ratio'], df['amt_now'])
    days_str = df['days'].astype(str)
    
    close_price = pd.to_numeric(df[COL.STD_PRICE], errors='coerce').fillna(0)
    limit_price = pd.to_numeric(df[COL.LIMIT_UP_PRICE], errors='coerce').fillna(0)
    high_price = pd.to_numeric(df[COL.HIGH], errors='coerce').fillna(0)

    # 2. 状态判定
    is_limit_up = (COL.LIMIT_UP_DOWN_STATUS in df.columns) & (df[COL.LIMIT_UP_DOWN_STATUS] == '涨停')
    is_limit_down = (COL.LIMIT_UP_DOWN_STATUS in df.columns) & (df[COL.LIMIT_UP_DOWN_STATUS] == '跌停')
    
    # 今日炸板：最高触板但收盘未板
    is_zhaban = (high_price >= limit_price) & (close_price < limit_price) & (limit_price > 0)
    
    # 断板判定
    if days_yest is not None:
        is_duanban = (days_yest >= 1) & (~is_limit_up)
    else:
        # 回退逻辑：如果缺失昨日连板数，尝试用状态推断（不太准确，建议上游传入）
        is_yest_limit_up = (COL.LIMIT_UP_DOWN_STATUS in df.columns) & (df[COL.LIMIT_UP_DOWN_STATUS] == '涨停') # 注意：这里df已经包含的是get_lianban_data返回的状态，通常是当日的，所以此逻辑仅作兜底
        is_duanban = is_yest_limit_up & (~is_limit_up)

    # 3. 标签组件构建
    lianban_tags = vol_level + days_str + '板'
    shouban_tags = vol_level + '首板'
    duanban_tags = vol_level + '断板'
    zhaban_tags = vol_level + '炸板'
    dazhang_tags = vol_level + '大涨'
    dadie_tags = vol_level + '大跌'

    # 4. 优先级判断条件
    conditions = [
        (df['pct_chg'] >= 33),               # 1. 新股
        is_limit_down,                       # 2. 今日跌停
        is_limit_up & (df['days'] >= 2),     # 3. 连板
        is_limit_up & (df['days'] == 1),     # 4. 首板
        is_duanban & is_limit_down,          # 5. 跌停断板
        is_duanban,                          # 6. 断板
        is_zhaban,                           # 7. 炸板
        (df['pct_chg'] >= 5),                # 8. 大涨
        (df['pct_chg'] <= -5),               # 9. 大跌
        (df['ratio'] >= 3.0) & (df['amt_now'] >= 1e6), # 10. 突发爆量
        (df['ratio'] >= 2.0) & (df['amt_now'] >= 1e6)  # 11. 一般放量
    ]

    choices = [
        '新股上市',
        '今日跌停',
        lianban_tags,
        shouban_tags,
        '跌停断板',
        duanban_tags,
        zhaban_tags,
        dazhang_tags,
        dadie_tags,
        '突发爆量',
        '一般放量'
    ]

    df[COL.STRUCTURE_TAG] = np.select(conditions, choices, default='--')
    return df


# ==================== 公共接口函数 ====================

def build_auction_tags(today_date: datetime, prev_date: datetime) -> pd.DataFrame:
    """
    构建竞价标签
    """
    today_date = ensure_datetime(today_date)
    prev_date = ensure_datetime(prev_date)
    
    # 1. 数据读取
    df_today = read_market_data(today_date, '竞价行情')
    df_yest_close = read_market_data(prev_date, '收盘行情')
    df_yest_auc = read_market_data(prev_date, '竞价行情')
    
    if df_today.empty:
        return pd.DataFrame()
    
    # 2. 注入连板与状态数据 (重要：获取昨日状态)
    df_lianban = get_lianban_data(prev_date)
    if not df_lianban.empty:
        cols_to_merge = [COL.CODE, COL.CONSECUTIVE_LIMIT_UP_DAYS]
        if COL.LIMIT_UP_DOWN_STATUS in df_lianban.columns:
            cols_to_merge.append(COL.LIMIT_UP_DOWN_STATUS)
        df_today = df_today.merge(df_lianban[cols_to_merge], on=COL.CODE, how='left')
    
    # 3. 数据准备与计算
    # 竞价阶段：对比的是昨日竞价金额
    df_calc = _prepare_base_data(df_today, df_yest_auc, df_yest_close)
    df_result = _generate_auction_logic(df_calc)

    # 4. 格式化输出
    output = df_result[[COL.CODE, COL.NAME, COL.STRUCTURE_TAG, 'days', 'ratio', 'pct_chg']].copy()
    output.columns = ['股票代码', '股票简称', '竞价标签', '连续涨停天数', '竞价放量倍数', '竞价涨幅']
    output['连续涨停天数'] = output['连续涨停天数'].astype(int)

    # 5. 【新增】添加状态标记列（与收盘标签保持一致）
    # 直接从 df_result 获取已清洗的数据，避免重复 merge 和转换
    prices = df_result[COL.STD_PRICE].values
    limit_ups = df_result[COL.LIMIT_UP_PRICE].values
    limit_downs = df_result[COL.LIMIT_DOWN_PRICE].values
    chgs = df_result['pct_chg'].values
    
    # 使用工具函数判断涨停（价格接近涨停价且涨跌幅>9%）
    output['is_limit_up'] = calculate_limit_up_numpy(prices, limit_ups, chgs)
    
    # 跌停判定：价格接近跌停价
    output['is_limit_down'] = (prices > 0) & (np.abs(prices - limit_downs) < 0.01) & (chgs < -9.0)
    output['is_lianban'] = (output['连续涨停天数'] >= 2) & output['is_limit_up']
    output['is_shouban'] = (output['连续涨停天数'] == 1) & output['is_limit_up']
    output['is_big_up'] = output['竞价涨幅'] >= 5.0
    output['is_big_down'] = output['竞价涨幅'] <= -5.0
    # 竞价阶段没有炸板概念（只有开盘状态）
    output['is_zhaban'] = False

    return output


def build_close_tags(today_date: datetime, prev_date: datetime) -> pd.DataFrame:
    """
    构建收盘标签
    """
    today_date = ensure_datetime(today_date)
    prev_date = ensure_datetime(prev_date)
    
    # 1. 数据读取
    df_today = read_market_data(today_date, '收盘行情')
    df_yest_close = read_market_data(prev_date, '收盘行情')
    
    if df_today.empty:
        return pd.DataFrame()
    
    # 2. 注入今日连板数据
    df_lianban_today = get_lianban_data(today_date)
    if not df_lianban_today.empty:
        cols = [COL.CODE, COL.CONSECUTIVE_LIMIT_UP_DAYS, COL.LIMIT_UP_DOWN_STATUS]
        cols = [c for c in cols if c in df_lianban_today.columns]
        df_today = df_today.merge(df_lianban_today[cols], on=COL.CODE, how='left')
    
    # 3. 获取昨日连板数据（用于判断断板）
    df_lianban_yest = get_lianban_data(prev_date)
    days_yest_series = None
    
    if not df_lianban_yest.empty:
        # 创建一个临时的映射表
        yest_map = df_lianban_yest.set_index(COL.CODE)[COL.CONSECUTIVE_LIMIT_UP_DAYS]
        days_yest_series = df_today[COL.CODE].map(yest_map).fillna(0)
    else:
        days_yest_series = pd.Series(0, index=df_today.index)

    # 4. 数据准备与计算
    # 收盘阶段：对比的是昨日收盘金额
    df_calc = _prepare_base_data(df_today, df_yest_close, df_yest_close)
    df_result = _generate_close_logic(df_calc, days_yest=days_yest_series)
    
    # 5. 格式化输出
    # 将昨日连板天数加入结果以便后续分析
    df_result['days_yest'] = days_yest_series.values
    
    # 获取状态标记（从 _generate_close_logic 内部计算的逻辑复用）
    close_price = pd.to_numeric(df_result[COL.STD_PRICE], errors='coerce').fillna(0)
    limit_price = pd.to_numeric(df_result[COL.LIMIT_UP_PRICE], errors='coerce').fillna(0)
    high_price = pd.to_numeric(df_result[COL.HIGH], errors='coerce').fillna(0)
    
    is_limit_up = (COL.LIMIT_UP_DOWN_STATUS in df_result.columns) & (df_result[COL.LIMIT_UP_DOWN_STATUS] == '涨停')
    is_limit_down = (COL.LIMIT_UP_DOWN_STATUS in df_result.columns) & (df_result[COL.LIMIT_UP_DOWN_STATUS] == '跌停')
    is_zhaban = (high_price >= limit_price) & (close_price < limit_price) & (limit_price > 0)
    is_duanban = (days_yest_series >= 1) & (~is_limit_up)
    
    output = df_result[[COL.CODE, COL.NAME, COL.STRUCTURE_TAG, 'days', 'days_yest', 'ratio', 'pct_chg']].copy()
    output.columns = ['股票代码', '股票简称', '收盘标签', '连续涨停天数', '昨日连板天数', '放量倍数', '收盘涨幅']
    output['连续涨停天数'] = output['连续涨停天数'].astype(int)
    output['昨日连板天数'] = output['昨日连板天数'].astype(int)
    
    # 添加状态标记列
    output['is_limit_up'] = is_limit_up
    output['is_limit_down'] = is_limit_down
    output['is_zhaban'] = is_zhaban
    output['is_duanban'] = is_duanban
    output['is_lianban'] = (output['连续涨停天数'] >= 2) & is_limit_up
    output['is_shouban'] = (output['连续涨停天数'] == 1) & is_limit_up
    output['is_big_up'] = output['收盘涨幅'] >= 5.0
    output['is_big_down'] = output['收盘涨幅'] <= -5.0
    
    return output


def build_merged_tags(today_date: datetime, prev_date: datetime) -> pd.DataFrame:
    """
    构建合并标签（竞价.收盘）
    """
    # 获取两份数据
    df_auction = build_auction_tags(today_date, prev_date)
    df_close = build_close_tags(today_date, prev_date)
    
    if df_auction.empty:
        return pd.DataFrame()
        
    # 如果收盘尚未出数据，仅返回竞价
    if df_close.empty:
        df_auction['收盘标签'] = '--'
        df_auction['合并标签'] = df_auction['竞价标签'].apply(lambda x: '--' if x == '--' else f"{x}.--")
        df_auction['收盘涨幅'] = None
        return df_auction[['股票代码', '股票简称', '竞价标签', '收盘标签', '合并标签', '竞价涨幅', '收盘涨幅']]
    
    # 合并
    df_merged = pd.merge(
        df_auction[['股票代码', '股票简称', '竞价标签', '竞价涨幅']],
        df_close[['股票代码', '收盘标签', '收盘涨幅']],
        on='股票代码',
        how='outer'
    )
    
    # 填充处理
    df_merged[['竞价标签', '收盘标签']] = df_merged[['竞价标签', '收盘标签']].fillna('--')
    
    # 补全股票简称（如果竞价数据缺失，从收盘数据补，反之亦然）
    if df_merged['股票简称'].isnull().any():
        # 建立代码到名称的映射
        name_map = df_auction.set_index('股票代码')['股票简称'].to_dict()
        name_map.update(df_close.set_index('股票代码')['股票简称'].to_dict())
        df_merged['股票简称'] = df_merged['股票简称'].fillna(df_merged['股票代码'].map(name_map))
    
    # 生成组合标签（包含涨幅）
    def format_pct(pct):
        """格式化涨幅百分比"""
        if pd.isna(pct):
            return '--'
        return f"{pct:.1f}%"
    
    df_merged['合并标签'] = (
        df_merged['竞价标签'] + '.' + df_merged['收盘标签']
    )
    
    # 全空处理
    mask_all_empty = (df_merged['竞价标签'] == '--') & (df_merged['收盘标签'] == '--')
    df_merged.loc[mask_all_empty, '合并标签'] = '--'
    
    return df_merged[['股票代码', '股票简称', '竞价标签', '收盘标签', '合并标签', '竞价涨幅', '收盘涨幅']]


def get_tags_for_concepts(today_date: datetime, 
                          prev_date: Optional[datetime] = None, 
                          tag_type: str = 'merged') -> pd.DataFrame:
    """
    外部调用入口：为概念分析提供标签数据
    """
    from tools.date_utils import get_date_context
    
    if prev_date is None:
        date_ctx = get_date_context(today_date)
        prev_date = date_ctx['yesterday_datetime']
    
    tag_map = {
        'auction': (build_auction_tags, ['股票代码', '竞价标签']),
        'close': (build_close_tags, ['股票代码', '收盘标签']),
        'merged': (build_merged_tags, ['股票代码', '合并标签'])
    }
    
    func, cols = tag_map.get(tag_type, (None, None))
    if not func:
        raise ValueError(f"Unknown tag_type: {tag_type}")
        
    df = func(today_date, prev_date)
    return df[cols].copy() if not df.empty else pd.DataFrame(columns=cols)
