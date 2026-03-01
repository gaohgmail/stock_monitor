# -*- coding: utf-8 -*-
"""
Streamlit 指标卡片组件 - 带百分位视觉反馈
支持大卡片+小卡片组合布局
"""
import pandas as pd
from typing import Optional, Tuple

# ==================== 样式常量 ====================
class CardStyle:
    """卡片样式常量"""
    # 字号
    FONT_TITLE = "17px"
    FONT_VALUE = "24px"
    FONT_DELTA = "18px"
    FONT_PCT = "17px"
    FONT_PCT_SMALL = "16px"
    
    # 颜色
    COLOR_TEXT = "#333"
    COLOR_LABEL = "#666"
    COLOR_RED = "#d62728"
    COLOR_GREEN = "#2ca02c"
    COLOR_BORDER = "#eee"
    
    # 高亮样式
    HIGHLIGHT_BORDER = "border:2px solid #d62728;background:#fffdf5;"
    
    # 卡片基础样式
    CARD_BASE = (
        "min-width:80px;margin-bottom:16px;border-radius:8px;"
        "overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1);background:white;"
    )
    
    # 内容区域样式
    CONTENT_PAD = "padding:10px 12px 6px 12px;border-bottom:1px solid #eee;"
    
    # 标签样式
    LABEL_STYLE = (
        "color:#666;font-size:17px;margin-bottom:2px;"
        "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
    )
    
    # 值样式
    VALUE_STYLE = "font-size:24px;font-weight:bold;color:#333;white-space:nowrap;"


# ==================== 百分位视觉 ====================
def get_pct_visuals(val: float) -> Tuple[str, str, str, str]:
    """
    返回百分位值的视觉样式和文案
    
    Args:
        val: 百分位值 (0-100)
    
    Returns:
        (bg_color, text_color, sub_text, icon)
    """
    if pd.isna(val):
        return "#f0f2f6", "#999", "数据计算中", "⚪"
    
    if val >= 80:
        return "#FFC1C1", "#8B0000", f"🔥 {val:.1f}% 强势", "🔥"
    elif val <= 20:
        return "#C1FFC1", "#006400", f"❄️ {val:.1f}% 冰点", "❄️"
    elif val >= 60:
        return "#FFF3CD", "#856404", f"📈 {val:.1f}% 偏强", "📈"
    elif val <= 40:
        return "#D1ECF1", "#0C5460", f"📉 {val:.1f}% 偏弱", "📉"
    else:
        return "#f8f9fa", "#666", f"💧 {val:.1f}% 中性", "💧"


# ==================== 辅助函数 ====================
def _get_delta_color(delta: str, mode: str = "inverse") -> str:
    """
    获取delta的颜色
    
    Args:
        delta: 变化值字符串
        mode: "inverse" 红涨绿跌, "normal" 绿涨红跌
    
    Returns:
        颜色代码
    """
    is_positive = delta.startswith('+') or '▲' in delta
    if mode == "normal":
        return CardStyle.COLOR_GREEN if is_positive else CardStyle.COLOR_RED
    return CardStyle.COLOR_RED if is_positive else CardStyle.COLOR_GREEN


def _build_delta_html(delta: Optional[str], mode: str = "inverse") -> str:
    """构建delta显示HTML"""
    if delta:
        color = _get_delta_color(delta, mode)
        return f'<div style="margin-top:6px;font-size:{CardStyle.FONT_DELTA};color:{color};white-space:nowrap;">{delta}</div>'
    return f'<div style="margin-top:6px;font-size:{CardStyle.FONT_DELTA};white-space:nowrap;">&nbsp;</div>'


def _build_pct_html(pct_val: Optional[float], font_size: str = CardStyle.FONT_PCT) -> str:
    """构建百分位小卡片HTML"""
    if pct_val is not None and not pd.isna(pct_val):
        bg_color, text_color, sub_text, _ = get_pct_visuals(pct_val)
        return f'''<div style="background-color:{bg_color};color:{text_color};padding:4px 12px;font-size:{font_size};font-weight:500;text-align:center;white-space:nowrap;">
{sub_text}
</div>'''
    return ""


# ==================== 卡片渲染函数 ====================
def render_metric_with_subcard(
    col,
    label: str,
    value: str,
    pct_val: Optional[float] = None,
    delta: Optional[str] = None,
    delta_color: str = "inverse",
    highlight_border: bool = False
):
    """
    渲染大卡片+小卡片组合
    
    Args:
        col: streamlit 列对象
        label: 指标名称
        value: 主值显示
        pct_val: 百分位值 (可选)
        delta: 变化值 (可选)
        delta_color: 变化颜色模式 ("inverse"红涨绿跌, "normal"绿涨红跌)
        highlight_border: 是否显示高亮边框
    """
    if pct_val is None or pd.isna(pct_val):
        _render_simple_card(col, label, value, delta, delta_color, highlight_border)
        return
    
    delta_html = _build_delta_html(delta, delta_color)
    pct_html = _build_pct_html(pct_val)
    border_style = CardStyle.HIGHLIGHT_BORDER if highlight_border else ""
    
    html = f'''<div style="{CardStyle.CARD_BASE}{border_style}">
<div style="{CardStyle.CONTENT_PAD}">
<div style="{CardStyle.LABEL_STYLE}">{label}</div>
<div style="{CardStyle.VALUE_STYLE}">{value}</div>
{delta_html}
</div>
{pct_html}
</div>'''
    
    col.markdown(html, unsafe_allow_html=True)


def _render_simple_card(
    col,
    label: str,
    value: str,
    delta: Optional[str] = None,
    delta_color: str = "inverse",
    highlight_border: bool = False
):
    """渲染简化版卡片（无百分位）"""
    delta_html = _build_delta_html(delta, delta_color)
    border_style = CardStyle.HIGHLIGHT_BORDER if highlight_border else ""
    
    html = f'''<div style="{CardStyle.CARD_BASE}padding:10px 12px;{border_style}">
<div style="{CardStyle.LABEL_STYLE}">{label}</div>
<div style="{CardStyle.VALUE_STYLE}">{value}</div>
{delta_html}
</div>'''
    
    col.markdown(html, unsafe_allow_html=True)


def render_metric_with_color(
    col,
    label: str,
    value: str,
    value_color: Optional[str] = None,
    delta: Optional[str] = None
):
    """
    渲染带颜色值的卡片（用于核心溢价等指标）
    
    Args:
        col: streamlit 列对象
        label: 指标名称
        value: 主值显示
        value_color: 值的颜色
        delta: 变化值 (可选)
    """
    color = value_color or CardStyle.COLOR_TEXT
    delta_html = _build_delta_html(delta, "inverse")
    
    html = f'''<div style="{CardStyle.CARD_BASE}padding:10px 12px;">
<div style="{CardStyle.LABEL_STYLE}">{label}</div>
<div style="font-size:{CardStyle.FONT_VALUE};font-weight:bold;color:{color};white-space:nowrap;">{value}</div>
{delta_html}
</div>'''
    
    col.markdown(html, unsafe_allow_html=True)


def render_metric_with_color_and_pct(
    col,
    label: str,
    value: str,
    value_color: Optional[str] = None,
    pct_val: Optional[float] = None,
    delta: Optional[str] = None,
    sub_label: Optional[str] = None
):
    """
    渲染带颜色值+百分位的卡片（用于核心溢价、妖股溢价等指标）
    
    Args:
        col: streamlit 列对象
        label: 指标名称
        value: 主值显示
        value_color: 值的颜色
        pct_val: 百分位值 (可选)
        delta: 变化值 (可选)
        sub_label: 下标区域显示的名称（可选）
    """
    color = value_color or CardStyle.COLOR_TEXT
    
    # 构建delta或sub_label
    if delta:
        delta_html = _build_delta_html(delta, "inverse")
    elif sub_label:
        delta_html = f'<div style="margin-top:6px;font-size:14px;color:#888;white-space:nowrap;">{sub_label}</div>'
    else:
        delta_html = f'<div style="margin-top:6px;font-size:{CardStyle.FONT_DELTA};white-space:nowrap;">&nbsp;</div>'
    
    pct_html = _build_pct_html(pct_val)
    
    html = f'''<div style="{CardStyle.CARD_BASE}">
<div style="{CardStyle.CONTENT_PAD}">
<div style="{CardStyle.LABEL_STYLE}">{label}</div>
<div style="font-size:{CardStyle.FONT_VALUE};font-weight:bold;color:{color};white-space:nowrap;">{value}</div>
{delta_html}
</div>
{pct_html}
</div>'''
    
    col.markdown(html, unsafe_allow_html=True)


def render_combined_metric_card(
    col,
    label: str,
    value1: str,
    value2: str,
    pct_val1: Optional[float] = None,
    pct_val2: Optional[float] = None,
    delta1: Optional[str] = None,
    delta2: Optional[str] = None,
    separator: str = "/"
):
    """
    渲染合并卡片（两个指标合并在一张卡片）
    
    Args:
        col: streamlit 列对象
        label: 卡片标题
        value1: 第一个指标值
        value2: 第二个指标值
        pct_val1: 第一个指标的百分位值
        pct_val2: 第二个指标的百分位值
        delta1: 第一个指标的变化值
        delta2: 第二个指标的变化值
        separator: 值之间的分隔符
    """
    value_display = f"{value1}{separator}{value2}"
    
    # 构建delta显示
    if delta1 and delta2:
        color1 = _get_delta_color(delta1, "inverse")
        color2 = _get_delta_color(delta2, "inverse")
        delta_html = f'<div style="margin-top:6px;font-size:{CardStyle.FONT_DELTA};white-space:nowrap;"><span style="color:{color1};">{delta1}</span><span style="color:#888;">{separator}</span><span style="color:{color2};">{delta2}</span></div>'
    else:
        delta_html = f'<div style="margin-top:6px;font-size:{CardStyle.FONT_DELTA};white-space:nowrap;">&nbsp;</div>'
    
    # 构建双百分位小卡片
    pct_html = ""
    if pct_val1 is not None and pct_val2 is not None and not pd.isna(pct_val1) and not pd.isna(pct_val2):
        bg1, text1, sub1, _ = get_pct_visuals(pct_val1)
        bg2, text2, sub2, _ = get_pct_visuals(pct_val2)
        pct_html = f'''<div style="display:flex;width:100%;">
<div style="flex:1 1 0%;background-color:{bg1};color:{text1};padding:4px 8px;font-size:{CardStyle.FONT_PCT_SMALL};font-weight:500;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;border-right:1px solid rgba(255,255,255,0.3);">{sub1}</div>
<div style="flex:1 1 0%;background-color:{bg2};color:{text2};padding:4px 8px;font-size:{CardStyle.FONT_PCT_SMALL};font-weight:500;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{sub2}</div>
</div>'''
    elif pct_val1 is not None and not pd.isna(pct_val1):
        pct_html = _build_pct_html(pct_val1)
    elif pct_val2 is not None and not pd.isna(pct_val2):
        pct_html = _build_pct_html(pct_val2)
    
    html = f'''<div style="{CardStyle.CARD_BASE}">
<div style="{CardStyle.CONTENT_PAD}">
<div style="{CardStyle.LABEL_STYLE}">{label}</div>
<div style="{CardStyle.VALUE_STYLE}">{value_display}</div>
{delta_html}
</div>
{pct_html}
</div>'''
    
    col.markdown(html, unsafe_allow_html=True)
