# -*- coding: utf-8 -*-
"""
市场类型颜色配置与判断逻辑
用于统一处理缩量/平量/增量市场的颜色标识
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
import pandas as pd


# ==================== 配置 ====================
@dataclass(frozen=True)
class MarketTypeConfig:
    """市场类型配置"""
    THRESHOLD_LOW: float = -5.0   # 缩量阈值：低于-5%
    THRESHOLD_HIGH: float = 15.0  # 增量阈值：高于+15%
    
    # 颜色配置
    COLORS: Dict[str, Dict[str, str]] = None
    
    def __post_init__(self):
        object.__setattr__(self, 'COLORS', {
            '缩量': {'hex': '#2ca02c', 'rgb': 'rgb(44, 160, 44)', 'name': '绿色', 'emoji': '🟢'},
            '平量': {'hex': '#ff7f0e', 'rgb': 'rgb(255, 127, 14)', 'name': '橙色', 'emoji': '🟠'},
            '增量': {'hex': '#d62728', 'rgb': 'rgb(214, 39, 40)', 'name': '红色', 'emoji': '🔴'}
        })


# 全局配置实例
CONFIG = MarketTypeConfig()


# ==================== 核心函数 ====================
def classify(change_percent: float) -> str:
    """
    根据变化百分比判断市场类型
    
    Args:
        change_percent: 成交额变化百分比（如 -5.5 表示下降5.5%）
    
    Returns:
        '缩量' | '平量' | '增量'
    """
    if pd.isna(change_percent):
        return '平量'
    if change_percent < CONFIG.THRESHOLD_LOW:
        return '缩量'
    if change_percent > CONFIG.THRESHOLD_HIGH:
        return '增量'
    return '平量'


def get_color(market_type: str, fmt: str = 'hex') -> str:
    """
    获取市场类型对应的颜色
    
    Args:
        market_type: '缩量' | '平量' | '增量'
        fmt: 颜色格式 - 'hex' | 'rgb' | 'name' | 'emoji'
    
    Returns:
        对应格式的颜色值
    """
    return CONFIG.COLORS.get(market_type, CONFIG.COLORS['平量']).get(fmt, '#ff7f0e')


def get_colors(changes: List[float]) -> List[str]:
    """
    批量获取颜色列表
    
    Args:
        changes: 变化百分比列表
    
    Returns:
        颜色列表
    """
    return [get_color(classify(c)) for c in changes]


def calc_changes(series: pd.Series) -> pd.Series:
    """
    计算环比变化百分比
    
    Args:
        series: 金额序列
    
    Returns:
        环比变化百分比序列
    """
    prev = series.shift(1)
    return ((series - prev) / prev * 100).round(2)


# ==================== DataFrame 工具 ====================
def add_market_type(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """
    为DataFrame添加市场类型列
    
    Args:
        df: DataFrame，需包含 {prefix}_总额 列
        prefix: 前缀，如 '竞价' 或 '收盘'
    
    Returns:
        添加了市场类型列的DataFrame
    """
    df = df.copy()
    amt_col = f'{prefix}_总额'
    
    if amt_col not in df.columns:
        return df
    
    # 计算环比和市场类型
    changes = calc_changes(df[amt_col])
    df[f'{prefix}总额环比%'] = changes
    df[f'{prefix}市场类型'] = changes.apply(classify)
    
    return df


def get_colors_from_df(df: pd.DataFrame, prefix: str) -> List[str]:
    """
    从DataFrame获取颜色列表
    
    Args:
        df: DataFrame，包含 {prefix}_总额 列
        prefix: 前缀，如 '竞价' 或 '收盘'
    
    Returns:
        颜色列表
    """
    amt_col = f'{prefix}_总额'
    if amt_col not in df.columns:
        return [get_color('平量')] * len(df)
    
    changes = calc_changes(df[amt_col]).fillna(0)
    return get_colors(changes.tolist())


# ==================== 显示工具 ====================
def get_full_name(market_type: str) -> str:
    """获取完整名称"""
    names = {'缩量': '缩量市场', '平量': '平量市场', '增量': '增量市场'}
    return names.get(market_type, '平量市场')


def get_emoji_name(market_type: str) -> str:
    """获取带emoji的名称"""
    return f"{get_color(market_type, 'emoji')} {get_full_name(market_type)}"


def get_definition_text() -> str:
    """获取市场类型定义文本"""
    return f"""**市场类型定义：**
- {get_emoji_name('缩量')}: 总额较昨日 **< {CONFIG.THRESHOLD_LOW}%**
- {get_emoji_name('平量')}: 总额较昨日 **{CONFIG.THRESHOLD_LOW}% ~ +{CONFIG.THRESHOLD_HIGH}%**
- {get_emoji_name('增量')}: 总额较昨日 **> +{CONFIG.THRESHOLD_HIGH}%**"""


# ==================== 类封装（向后兼容） ====================
class MarketTypeClassifier:
    """市场类型分类器（向后兼容）"""
    
    @staticmethod
    def classify(change_percent: float) -> str:
        return classify(change_percent)
    
    @staticmethod
    def classify_series(changes: pd.Series) -> pd.Series:
        return changes.apply(classify)
    
    @staticmethod
    def add_market_type_to_df(df: pd.DataFrame, stage: str) -> pd.DataFrame:
        return add_market_type(df, stage)


class MarketTypeColors:
    """市场类型颜色工具（向后兼容）"""
    
    @staticmethod
    def get_color(market_type: str, format: str = 'hex') -> str:
        return get_color(market_type, format)
    
    @staticmethod
    def get_colors_from_df(df: pd.DataFrame, stage: str, amt_col: str = None) -> list:
        if amt_col:
            changes = calc_changes(df[amt_col]).fillna(0)
            return get_colors(changes.tolist())
        return get_colors_from_df(df, stage)
    
    @staticmethod
    def get_full_name(market_type: str) -> str:
        return get_full_name(market_type)
    
    @staticmethod
    def get_emoji_with_name(market_type: str) -> str:
        return get_emoji_name(market_type)
    
    @staticmethod
    def get_all_colors(format: str = 'hex') -> Dict[str, str]:
        return {k: v.get(format, v['hex']) for k, v in CONFIG.COLORS.items()}
    
    @staticmethod
    def get_definition_markdown() -> str:
        return get_definition_text()


# ==================== 便捷函数 ====================
classify_market = classify
get_market_color = get_color
get_market_emoji = lambda mt: get_color(mt, 'emoji')


# ==================== 测试 ====================
if __name__ == "__main__":
    print("测试分类:")
    for pct in [-10, 0, 5, 20]:
        print(f"  {pct:+.0f}% -> {classify(pct)}")
    
    print("\n测试颜色:")
    for mt in ['缩量', '平量', '增量']:
        print(f"  {mt}: {get_color(mt)} {get_emoji_name(mt)}")
    
    print("\n市场定义:")
    print(get_definition_text())
