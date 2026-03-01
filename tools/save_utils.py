# -*- coding: utf-8 -*-
"""
统一存盘工具模块

提供标准化的数据保存功能，所有分析模块统一使用此模块保存结果
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from tools.config import MARKET_REPORT_DIR


def save_dataframe(
    df: pd.DataFrame,
    filename: str,
    date: datetime,
    output_dir: Optional[str] = None,
    encoding: str = 'utf-8-sig',
    float_format: str = '%.2f',
    index: bool = False
) -> str:
    """
    保存DataFrame到CSV文件

    参数:
        df: 要保存的数据
        filename: 文件名（不含日期和扩展名）
        date: 日期，用于生成文件名
        output_dir: 输出目录（默认使用MARKET_REPORT_DIR）
        encoding: 编码格式
        float_format: 浮点数格式
        index: 是否保存索引

    返回:
        保存的文件路径
    """
    if df.empty:
        return ""

    # 确定输出目录
    if output_dir is None:
        output_dir = str(MARKET_REPORT_DIR)

    # 创建目录
    os.makedirs(output_dir, exist_ok=True)

    # 生成文件名
    date_str = date.strftime('%Y%m%d')
    file_path = os.path.join(output_dir, f"{filename}_{date_str}.csv")

    # 保存数据
    df.to_csv(
        file_path,
        index=index,
        encoding=encoding,
        float_format=float_format
    )

    return file_path


def save_limit_up_data(
    df_auction: pd.DataFrame,
    df_close: pd.DataFrame,
    date: datetime,
    output_dir: Optional[str] = None
) -> tuple:
    """
    保存涨停分析数据

    返回:
        (auction_path, close_path): 两个文件的路径
    """
    auction_path = ""
    close_path = ""

    if not df_auction.empty:
        auction_path = save_dataframe(
            df_auction,
            'limit_up_auction',
            date,
            output_dir
        )

    if not df_close.empty:
        close_path = save_dataframe(
            df_close,
            'limit_up_close',
            date,
            output_dir
        )

    return auction_path, close_path


def save_concept_data(
    df: pd.DataFrame,
    data_type: str,
    date: datetime,
    output_dir: Optional[str] = None
) -> str:
    """
    保存题材分析数据

    参数:
        df: 题材统计数据
        data_type: '竞价' 或 '收盘'
        date: 日期
        output_dir: 输出目录

    返回:
        保存的文件路径
    """
    filename = f"concept_stats_{'auction' if data_type == '竞价' else 'close'}"
    return save_dataframe(df, filename, date, output_dir)


def save_stock_details(
    df: pd.DataFrame,
    data_type: str,
    date: datetime,
    output_dir: Optional[str] = None
) -> str:
    """
    保存个股详情数据

    参数:
        df: 个股详情数据
        data_type: '竞价' 或 '收盘'
        date: 日期
        output_dir: 输出目录

    返回:
        保存的文件路径
    """
    filename = f"stock_details_{'auction' if data_type == '竞价' else 'close'}"
    return save_dataframe(df, filename, date, output_dir)


def save_sentiment_data(
    df: pd.DataFrame,
    date: datetime,
    output_dir: Optional[str] = None,
    filename: str = 'daily_sentiment_trend'
) -> str:
    """
    保存市场情绪数据

    参数:
        df: 情绪数据DataFrame
        date: 日期
        output_dir: 输出目录
        filename: 文件名前缀

    返回:
        保存的文件路径
    """
    if df.empty:
        return ""

    # 移除内部使用的_raw_date列
    save_cols = [c for c in df.columns if c != '_raw_date']

    return save_dataframe(
        df[save_cols],
        filename,
        date,
        output_dir
    )
