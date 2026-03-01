# -*- coding: utf-8 -*-
# tools/utils.py

import sys
import os
import subprocess
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional, Union, Tuple
from io import StringIO

# 尝试导入 streamlit
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    st = None
    HAS_STREAMLIT = False

from tools.config import COLUMN_MAPPING, COL
from tools.cache_config import cached_data, CACHE_TTL

# ==================== 1. 基础工具与日志 (Infrastructure) ====================

class Logger:
    """同时输出到控制台和文件的日志器"""
    def __init__(self, filename: str, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self.terminal = sys.stdout
        self.log_file = path / filename
        # 使用追加模式，防止覆盖
        self.log = open(self.log_file, "a", encoding='utf-8')

    def write(self, message: str):
        self.terminal.write(message)
        self.log.write(message)
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


def conditional_cache_data(func):
    """兼容非 Streamlit 环境的缓存装饰器"""
    if HAS_STREAMLIT:
        return cached_data(ttl_seconds=CACHE_TTL['daily'])(func)
    return func


# ==================== 2. 高性能 I/O (High Performance I/O) ====================

@conditional_cache_data
def safe_read_csv(
    file_path: Path, 
    usecols: Optional[List[str]] = None,
    dtype_force_str: bool = True
) -> pd.DataFrame:
    """
    【高性能】安全读取 CSV
    
    优化点：
    1. 默认 engine='c' 提速
    2. dtype=str 强制全字符串读取，防止 '000001' 变 1，确保数据安全
    3. 支持 usecols 列裁剪，减少内存占用
    """
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    if not file_path.exists():
        return pd.DataFrame()

    # 基础参数：C引擎，不处理低内存块，防止类型推断错误
    read_params = {
        'engine': 'c',
        'low_memory': False,
        'usecols': usecols,
        # 核心防御：默认全读为字符串，后续再清洗转数值
        # 这比单独指定 {'股票代码': str} 更稳健，因为原始列名可能还没被 map 过来
        'dtype': str if dtype_force_str else None 
    }

    # 优先尝试 utf-8-sig (标准)，失败回退 gbk
    try:
        return pd.read_csv(file_path, encoding='utf-8-sig', **read_params)
    except UnicodeDecodeError:
        try:
            return pd.read_csv(file_path, encoding='gbk', **read_params)
        except Exception as e:
            print(f"⚠️ 文件读取失败 (GBK): {file_path} - {e}")
            return pd.DataFrame()
    except Exception as e:
        print(f"⚠️ 文件读取异常: {file_path} - {e}")
        return pd.DataFrame()


# ==================== 3. 向量化清洗与计算 (Vectorized Operations) ====================

def _vectorized_standardize_code(series: pd.Series) -> pd.Series:
    """
    【向量化】标准化股票代码内部逻辑
    速度比 .apply() 快 50-100 倍
    """
    # 1. 确保是字符串并清理非数字字符
    s = series.astype(str).str.replace(r'\D', '', regex=True)
    
    # 2. 补齐 6 位
    s = s.str.zfill(6)
    
    # 3. 构造结果容器 (默认 sz)
    prefixes = np.full(len(s), 'sz', dtype=object)
    
    # 4. 向量化判断前缀
    # 获取首字母
    first_char = s.str[0]
    
    # 6开头 -> sh
    prefixes[first_char == '6'] = 'sh'
    
    # 4/8/9开头 -> bj
    is_bj = first_char.isin(['4', '8', '9'])
    prefixes[is_bj] = 'bj'
    
    # 5. 拼接
    return pd.Series(prefixes, index=s.index) + s


@conditional_cache_data
def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    【标准化】清洗 DataFrame
    1. 去除列名空格
    2. 应用 COLUMN_MAPPING 重命名
    3. 标准化股票代码 (向量化)
    4. 去除重复列
    """
    if df.empty:
        return df

    # 1. 清理列名
    df.columns = df.columns.str.strip()
    
    # 2. 映射列名 (从 config 获取)
    df = df.rename(columns=COLUMN_MAPPING)
    
    # 3. 去重列 (保留第一个)
    df = df.loc[:, ~df.columns.duplicated()]

    # 4. 标准化代码
    if COL.CODE in df.columns:
        df[COL.CODE] = _vectorized_standardize_code(df[COL.CODE])
    
    return df


def ensure_numeric_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """
    【批量】确保指定列为数值类型
    无法转换的设为 NaN，然后可选填充
    """
    if df.empty or not cols:
        return df
    
    for c in cols:
        if c in df.columns:
            # 先转字符串再转数值，处理各种奇怪格式
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', ''), errors='coerce')
    
    return df


# ==================== 4. 涨停跌停计算 (Limit Up/Down) ====================

def calculate_limit_up_numpy(prices: np.ndarray, limit_up_prices: np.ndarray, chgs: np.ndarray = None, tolerance: float = 0.001, change_threshold: float = 9.0) -> np.ndarray:
    """
    【向量化】计算涨停状态
    
    参数:
        prices: 当前价格数组
        limit_up_prices: 涨停价格数组
        chgs: 涨跌幅数组（可选）
        tolerance: 价格容差 (默认0.001元)
        change_threshold: 涨跌幅阈值 (默认9.0%)
    
    返回:
        布尔数组，True表示涨停
    """
    is_limit = (prices > 0) & (np.abs(prices - limit_up_prices) < tolerance)
    if chgs is not None:
        is_limit = is_limit & (chgs > change_threshold)
    return is_limit


def calculate_limit_down_numpy(prices: np.ndarray, limit_down_prices: np.ndarray, tolerance: float = 0.01) -> np.ndarray:
    """
    【向量化】计算跌停状态
    """
    return np.abs(prices - limit_down_prices) < tolerance


# ==================== 5. 热点关键词标记 ====================

def add_hot_keywords_vectorized(
    df: pd.DataFrame,
    keywords: Optional[List[str]] = None,
    concept_col: str = COL.CONCEPT,
    name_col: str = COL.NAME
) -> pd.DataFrame:
    """
    【向量化】添加热点关键词标记
    修复了列表不可哈希的问题，改用字符串拼接
    """
    from tools.config import HOT_KEYWORDS
    
    if df.empty:
        return df
    
    # 使用默认关键词
    if keywords is None:
        keywords = HOT_KEYWORDS
    
    if not keywords:
        return df
    
    # 1. 构造搜索文本 (概念 + 名称)
    # 使用 fillna('') 防止 NaN 传染
    search_series = pd.Series("", index=df.index)
    if concept_col in df.columns:
        search_series += df[concept_col].astype(str).fillna('')
    if name_col in df.columns:
        search_series += " " + df[name_col].astype(str).fillna('')
    
    # 2. 向量化匹配
    # 创建一个临时结果列
    df['热点关键词'] = ""
    
    # 循环关键词，每次向量化更新匹配的行
    # 虽然这里有循环，但关键词列表通常很短 (<50)，比逐行 apply 快得多
    results = []
    for kw in keywords:
        # 找出包含该关键词的行
        mask = search_series.str.contains(kw, regex=False)
        if mask.any():
            results.append((kw, mask))
    
    # 3. 合并结果
    if results:
        # 更优解：利用 vectorization 逐步拼接
        final_series = pd.Series("", index=df.index, dtype=str)
        first = True
        for kw, mask in results:
            if first:
                final_series.loc[mask] = kw
                first = False
            else:
                # 如果已有值且当前也匹配，加逗号
                # 使用 pd.Series.loc 避免类型错误
                existing_mask = mask & (final_series != "")
                new_mask = mask & (final_series == "")
                
                if existing_mask.any():
                    final_series.loc[existing_mask] += "," + kw
                if new_mask.any():
                    final_series.loc[new_mask] = kw
        df['热点关键词'] = final_series
    
    return df


# ==================== 6. 文件操作工具 ====================

def ensure_dir(path: Path) -> Path:
    """确保目录存在，返回 Path 对象"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_to_csv(df: pd.DataFrame, file_path: Path, index: bool = False):
    """安全保存 DataFrame 到 CSV"""
    if df.empty:
        return
    ensure_dir(file_path.parent)
    df.to_csv(file_path, index=index, encoding='utf-8-sig')


# ==================== 7. 系统工具 ====================

def open_file_or_dir(path: Path):
    """使用系统默认程序打开文件或目录"""
    if not path.exists():
        print(f"路径不存在: {path}")
        return
    
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.run(['open', path])
    else:
        subprocess.run(['xdg-open', path])


# ==================== 8. DataFrame 条件筛选 (从 utils_dataframe.py 合并) ====================

def apply_condition(df: pd.DataFrame, column: str, operator: str, value) -> pd.DataFrame:
    """
    应用单个筛选条件 (移除 eval，使用原生 Pandas 操作)
    """
    if df.empty or column not in df.columns:
        return df

    try:
        if operator == '>':
            return df[df[column] > float(value)]
        elif operator == '<':
            return df[df[column] < float(value)]
        elif operator == '>=':
            return df[df[column] >= float(value)]
        elif operator == '<=':
            return df[df[column] <= float(value)]
        elif operator == '==':
            # 兼容数值和字符串
            return df[df[column] == value]
        elif operator == '!=':
            return df[df[column] != value]
        elif operator == 'contains':
            return df[df[column].astype(str).str.contains(str(value), na=False, regex=False)]
        elif operator == 'not_contains':
            return df[~df[column].astype(str).str.contains(str(value), na=False, regex=False)]
        elif operator == 'in_list':
            val_list = value.split(',') if isinstance(value, str) else value
            return df[df[column].isin(val_list)]
    except Exception as e:
        print(f"Filter Error: {e}")
        return df
    
    return df
