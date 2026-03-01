# -*- coding: utf-8 -*-
"""
市场情绪看板 V2 - 卡片式布局
集成百分位计算与视觉反馈
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional, Any

from tools.config import COL
from ui.components.market_type_colors import MarketTypeColors
from ui.components.percentile_calculator import calculate_market_dna
from ui.components.streamlit_metric_card import (
    render_metric_with_subcard,
    render_metric_with_color_and_pct,
    render_combined_metric_card
)


# ==================== 配置常量 ====================
class Config:
    """配置常量"""
    # 颜色
    COLORS = {
        'bar_red': '#d62728',
        'bar_green': '#2ca02c',
        'line_red': '#d62728',
        'line_green': '#2ca02c',
        'line_blue': '#1f77b4',
        'line_orange': '#ff7f0e'
    }
    
    # 图表布局
    CHART_LAYOUT = dict(
        height=450,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(l=10, r=10, t=40, b=10),
        template="plotly_white",
        xaxis=dict(type='category', tickmode='auto', nticks=20)
    )
    
    # 百分位窗口
    JJ_WINDOW = 20  # 竞价阶段
    SP_WINDOW = 60  # 收盘阶段


# ==================== 工具函数 ====================
def _safe_get(df_row: pd.Series, key: str, default: Any = 0) -> Any:
    """安全获取数据值"""
    val = df_row.get(key, default)
    return default if pd.isna(val) else val


def _get_value_color(val: float) -> str:
    """根据正负值获取颜色"""
    if val > 0:
        return Config.COLORS['bar_red']
    elif val < 0:
        return Config.COLORS['bar_green']
    return "#333"


@st.cache_data(ttl=300)
def _process_market_data(df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """处理市场数据，计算双阶段百分位"""
    if df.empty:
        return df
    
    df = df.copy()
    
    if '日期' in df.columns:
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.sort_values('日期').reset_index(drop=True)
    
    df = calculate_market_dna(df, prefix='竞价_', window=Config.JJ_WINDOW)
    df = calculate_market_dna(df, prefix='收盘_', window=window)
    
    return df


# ==================== 图表工厂 ====================
def _create_volume_sentiment_chart(df: pd.DataFrame, prefix: str) -> go.Figure:
    """创建 [总额 vs 涨跌比] 组合图"""
    col_amt = f'{prefix}_总额'
    col_ratio = f'{prefix}_全场涨跌比'
    
    if col_amt not in df.columns or df.empty:
        return go.Figure()

    colors = MarketTypeColors.get_colors_from_df(df, prefix)
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig.add_trace(
        go.Bar(
            x=df['日期'], y=df[col_amt],
            name=f"{prefix}总额(亿)",
            marker_color=colors, opacity=0.7
        ),
        secondary_y=False
    )
    
    if col_ratio in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df['日期'], y=df[col_ratio],
                name="全场涨跌比",
                line=dict(color=Config.COLORS['line_blue'], width=2)
            ),
            secondary_y=True
        )
        
    fig.add_hline(y=1, line_dash="dot", line_color="gray", secondary_y=True)
    fig.update_layout(**Config.CHART_LAYOUT)
    fig.update_yaxes(title_text="成交额 (亿)", secondary_y=False)
    fig.update_yaxes(title_text="涨跌比", secondary_y=True)
    
    return fig


def _create_limit_chart(df: pd.DataFrame, prefix: str) -> go.Figure:
    """创建 [涨停 vs 跌停] 堆叠图"""
    col_up = f'{prefix}_涨停'
    col_down = f'{prefix}_跌停'
    
    if col_up not in df.columns or df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df['日期'], y=df[col_up],
        name="涨停数", marker_color=Config.COLORS['bar_red']
    ))
    
    if col_down in df.columns:
        fig.add_trace(go.Bar(
            x=df['日期'], y=df[col_down],
            name="跌停数", marker_color=Config.COLORS['bar_green']
        ))
        
    fig.update_layout(**Config.CHART_LAYOUT)
    return fig


def _create_strength_chart(df: pd.DataFrame, prefix: str) -> go.Figure:
    """创建 [强力 vs 极弱] 对比图"""
    col_strong = f'{prefix}_强力'
    col_weak = f'{prefix}_极弱'
    
    if col_strong not in df.columns or df.empty:
        return go.Figure()
        
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['日期'], y=df[col_strong],
        name="强力股(>7%)",
        line=dict(color=Config.COLORS['line_red'], width=2),
        fill='tozeroy'
    ))
    
    if col_weak in df.columns:
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df[col_weak],
            name="极弱股(<-7%)",
            line=dict(color=Config.COLORS['line_green'], width=2),
            fill='tozeroy'
        ))
        
    fig.update_layout(**Config.CHART_LAYOUT)
    return fig


def _create_top15_chart(df: pd.DataFrame) -> go.Figure:
    """创建 [Top15占比] 趋势图"""
    has_jj = '竞价_前15占比' in df.columns
    has_sp = '收盘_前15占比' in df.columns
    
    if (not has_jj and not has_sp) or df.empty:
        return go.Figure()
    
    fig = go.Figure()
    
    if has_jj:
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df['竞价_前15占比'],
            name="竞价前15占比(%)",
            line=dict(color=Config.COLORS['line_blue'], width=2)
        ))
        
    if has_sp:
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df['收盘_前15占比'],
            name="收盘前15占比(%)",
            line=dict(color=Config.COLORS['line_orange'], width=2)
        ))
        
    fig.update_layout(**Config.CHART_LAYOUT)
    return fig


# ==================== 测试组件 ====================
def render_distribution_chart(df: pd.DataFrame):
    """绘制全场涨跌幅分布直方图"""
    st.subheader("📊 全场涨跌分布测试")

    if df.empty:
        st.info("暂无数据可展示")
        return

    target_col = COL.PCT_CHG
    if target_col not in df.columns:
        st.error(f"❌ 数据缺失核心列: {target_col}")
        return

    series_data = pd.to_numeric(df[target_col], errors='coerce').dropna()

    up_count = (series_data > 0).sum()
    down_count = (series_data < 0).sum()
    zero_count = (series_data == 0).sum()
    median_val = series_data.median()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("上涨家数", f"{up_count}", delta_color="normal")
    c2.metric("下跌家数", f"{down_count}", delta_color="inverse")
    c3.metric("平盘家数", f"{zero_count}")
    c4.metric("涨跌中位数", f"{median_val:.2f}%")

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=series_data,
        xbins=dict(start=-20, end=20, size=1),
        marker_color=Config.COLORS['line_blue'],
        opacity=0.75,
        name='家数'
    ))
    fig.add_vline(x=0, line_width=2, line_dash="dash", line_color="gray")
    fig.update_layout(
        title="市场涨跌幅分布 (Bins=1%)",
        xaxis_title="涨跌幅 (%)",
        yaxis_title="股票数量 (家)",
        bargap=0.1,
        template="plotly_white",
        height=400,
        hovermode="x unified"
    )
    st.plotly_chart(fig, width='stretch')
    
    with st.expander("🔍 查看原始数据 (Top 5 & Bottom 5)"):
        top5 = df.nlargest(5, target_col)[[COL.CODE, COL.NAME, target_col, COL.STD_AMOUNT]]
        bot5 = df.nsmallest(5, target_col)[[COL.CODE, COL.NAME, target_col, COL.STD_AMOUNT]]
        st.write("**涨幅前五:**")
        st.dataframe(top5, hide_index=True)
        st.write("**跌幅前五:**")
        st.dataframe(bot5, hide_index=True)


# ==================== KPI渲染 ====================
def _render_kpi_section(df: pd.DataFrame, prefix: str, title: str, latest: pd.Series, prev: pd.Series):
    """渲染KPI指标区域"""
    st.markdown(f"##### {title}")
    
    # 列布局：竞价8列，收盘10列
    cols = st.columns([1.2, 1, 1, 1, 1, 1, 0.75, 0.75, 0.75, 0.75]) if prefix == '收盘' else st.columns(8)
    
    # 1. 总额
    amt = _safe_get(latest, f'{prefix}_总额', 0)
    amt_diff = _safe_get(latest, f'{prefix}_资金增减', 0)
    amt_pct_change = _safe_get(latest, f'{prefix}_增减幅', 0)
    amt_pct_text = f"({amt_pct_change*100:+.2f}%)" if amt_pct_change else ""
    render_metric_with_subcard(
        cols[0], f"💰 {prefix}总额", f"{amt:.2f}亿",
        _safe_get(latest, f'{prefix}_成交额百分位', np.nan),
        f"{amt_diff:+.2f}亿 {amt_pct_text}"
    )
    
    # 2. 全场涨跌比（高亮）
    ratio = _safe_get(latest, f'{prefix}_全场涨跌比', 0)
    prev_ratio = _safe_get(prev, f'{prefix}_全场涨跌比', ratio)
    ratio_delta = ratio - prev_ratio if pd.notnull(prev_ratio) else 0
    render_metric_with_subcard(
        cols[1], "📊 全场涨跌比", f"{ratio:.2f}",
        _safe_get(latest, f'{prefix}_涨跌比_pct', np.nan),
        f"{ratio_delta:+.2f}",
        highlight_border=True
    )
    
    # 3. 上海涨跌比
    render_metric_with_subcard(
        cols[2], "🏢 上海涨跌比", f"{_safe_get(latest, f'{prefix}_上海涨跌比', 0):.2f}",
        None, f"{int(_safe_get(latest, f'{prefix}_上海额_diff', 0)):+}亿"
    )
    
    # 4. 创业涨跌比
    render_metric_with_subcard(
        cols[3], "🚀 创业涨跌比", f"{_safe_get(latest, f'{prefix}_创业涨跌比', 0):.2f}",
        _safe_get(latest, f'{prefix}_创业额百分位', np.nan),
        f"{int(_safe_get(latest, f'{prefix}_创业额_diff', 0)):+}亿"
    )
    
    # 5. 涨停/跌停
    render_combined_metric_card(
        cols[4], "📈 涨停/跌停",
        f"{int(_safe_get(latest, f'{prefix}_涨停', 0))}家",
        f"{int(_safe_get(latest, f'{prefix}_跌停', 0))}家",
        _safe_get(latest, f'{prefix}_涨停数百分位', np.nan),
        _safe_get(latest, f'{prefix}_跌停数百分位', np.nan),
        f"{int(_safe_get(latest, f'{prefix}_涨停_diff', 0)):+d}家",
        f"{int(_safe_get(latest, f'{prefix}_跌停_diff', 0)):+d}家"
    )
    
    # 6. 强力/极弱
    render_combined_metric_card(
        cols[5], "💪 强力/极弱",
        f"{int(_safe_get(latest, f'{prefix}_强力', 0))}家",
        f"{int(_safe_get(latest, f'{prefix}_极弱', 0))}家",
        _safe_get(latest, f'{prefix}_强力数百分位', np.nan),
        _safe_get(latest, f'{prefix}_极弱数百分位', np.nan),
        f"{int(_safe_get(latest, f'{prefix}_强力_diff', 0)):+d}家",
        f"{int(_safe_get(latest, f'{prefix}_极弱_diff', 0)):+d}家"
    )
    
    # 7. 核心指标（竞价/收盘不同）
    _render_core_metrics(cols, prefix, latest)
    
    st.markdown("---")


def _render_core_metrics(cols, prefix: str, latest: pd.Series):
    """渲染核心指标（竞价/收盘不同）"""
    if prefix == '竞价':
        # 竞价：核心溢价、妖股溢价
        core = _safe_get(latest, '竞价_核心溢价', 0)
        render_metric_with_color_and_pct(
            cols[6], "🎯 核心溢价", f"{core:.2f}%",
            _get_value_color(core),
            _safe_get(latest, '竞价_核心溢价_pct', np.nan), ""
        )
        
        yao = _safe_get(latest, '竞价_妖股溢价', 0)
        render_metric_with_color_and_pct(
            cols[7], "🎭 妖股溢价", f"{yao:.2f}%",
            _get_value_color(yao),
            _safe_get(latest, '竞价_妖股溢价_pct', np.nan), ""
        )
    else:
        # 收盘：核心赚钱、妖股赚钱、核心承接、妖股承接
        metrics = [
            ("💰 核心赚钱", '收盘_核心赚钱', '收盘_核心赚钱_pct', cols[6]),
            ("💎 妖股赚钱", '收盘_妖股赚钱', '收盘_妖股赚钱_pct', cols[7]),
            ("🔗 核心承接", '收盘_核心承接', '收盘_核心承接_pct', cols[8]),
            ("🤝 妖股承接", '收盘_妖股承接', '收盘_妖股承接_pct', cols[9]),
        ]
        for label, val_key, pct_key, col in metrics:
            val = _safe_get(latest, val_key, 0)
            render_metric_with_color_and_pct(
                col, label, f"{val:.2f}%",
                _get_value_color(val),
                _safe_get(latest, pct_key, np.nan), ""
            )


# ==================== 图表渲染 ====================
def _render_trend_charts(df: pd.DataFrame):
    """渲染趋势分析图表"""
    st.markdown("##### 📈 趋势分析")
    
    tabs = st.tabs(["资金情绪", "涨跌停结构", "强弱结构", "抱团占比"])
    
    chart_configs = [
        ("资金情绪", _create_volume_sentiment_chart, "金额 vs 涨跌比"),
        ("涨跌停结构", _create_limit_chart, "涨停/跌停"),
        ("强弱结构", _create_strength_chart, "强力/极弱"),
    ]
    
    for idx, (tab_name, chart_func, desc) in enumerate(chart_configs):
        with tabs[idx]:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**竞价：{desc}**")
                st.plotly_chart(chart_func(df, '竞价'), width='stretch')
            with c2:
                st.markdown(f"**收盘：{desc}**")
                st.plotly_chart(chart_func(df, '收盘'), width='stretch')

    with tabs[3]:
        st.markdown("**市场集中度：Top15 成交额占比**")
        st.plotly_chart(_create_top15_chart(df), width='stretch')


def _render_data_table(df: pd.DataFrame):
    """渲染数据明细表格"""
    st.markdown("---")
    st.markdown("##### 📋 数据明细")
    
    with st.expander("查看详细数据表", expanded=False):
        st.dataframe(
            df.sort_values('日期', ascending=False),
            width='stretch',
            height=400
        )


# ==================== 主入口 ====================
def render_sentiment_dashboard(df: pd.DataFrame, window: int = 60):
    """
    市场情绪看板主入口
    
    Args:
        df: 市场情绪数据
        window: 百分位滚动窗口（默认60天）
    """
    if df.empty:
        st.warning("⚠️ 暂无分析数据，请检查数据源。")
        return
    
    df = _process_market_data(df, window=window)
        
    if '日期' in df.columns:
        df = df.sort_values('日期')
    
    has_close_data = '收盘_总额' in df.columns and (df['收盘_总额'].iloc[-1] > 0)
    
    # 标题栏
    latest = df.iloc[-1]
    latest_date = latest['日期']
    
    summary_parts = []
    for key, label, unit in [
        ('竞价_上海额', '上海总额', '亿'),
        ('竞价_创业额', '创业板总额', '亿'),
        ('竞价_上证涨跌幅', '上海涨跌幅', '%'),
        ('竞价_创业涨跌幅', '创业板涨跌幅', '%'),
    ]:
        if key in latest:
            val = latest[key]
            summary_parts.append(f"{label}: {val:.2f}{unit}")
    
    st.markdown("### 📊 市场情绪 V2 - DNA百分位版")
    st.caption(f"分析日期: {latest_date} ( {' | '.join(summary_parts)} )")
    st.info("💡 百分位说明：水位>=80%为强势(🔥)，<=20%为冰点(❄️)，跌停/极弱已执行反转计算，竞价20收盘60窗口滚动")
    st.markdown("---")
    
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    _render_kpi_section(df, '竞价', '🚀 竞价阶段', latest, prev)
    
    if has_close_data:
        _render_kpi_section(df, '收盘', '🏁 收盘阶段', latest, prev)
    
    _render_trend_charts(df)
    _render_data_table(df)
