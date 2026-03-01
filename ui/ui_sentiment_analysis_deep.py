# -*- coding: utf-8 -*-
"""
情绪数据深度分析页面 - 情绪综合分趋势
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from typing import List, Optional


# ==================== 配置 ====================
CACHE_TTL = 3600
DATA_DAYS = 60

ZONES = [
    (0, 20, '#2ca02c', '冰点'),
    (20, 40, '#98df8a', '偏冷'),
    (40, 60, '#ffbb78', '中性'),
    (60, 80, '#ff9896', '偏暖'),
    (80, 100, '#d62728', '过热')
]

SENTIMENT_COLS = ['全场涨跌比', '强力', '极弱', '涨停', '跌停', '核心赚钱']
REVERSE_COLS = ['极弱', '跌停']

# 动态阈值配置
VOL_WINDOW = 20
ADJUST_FACTOR = 10
BASE_THRESHOLDS = [20, 40, 60, 80]
ZONE_LABELS = ['冰点', '偏冷', '中性', '偏暖', '过热']
BID_WINDOW = 10  # 竞价情绪分滚动窗口

# 颜色配置
COLORS = {
    '冰点': '#2ca02c', '偏冷': '#98df8a', '中性': '#ffbb78',
    '偏暖': '#ff9896', '过热': '#d62728',
    'line_blue': '#1f77b4', 'line_orange': '#ff7f0e',
    'line_green': '#2ca02c'
}


# ==================== 数据加载 ====================
@st.cache_data(ttl=CACHE_TTL)
def load_data() -> pd.DataFrame:
    """加载市场情绪数据"""
    from tools.data_loader import get_trade_dates
    from core.service_layer import market_service
    
    dates = get_trade_dates(count=DATA_DAYS)
    if not dates:
        return pd.DataFrame()
    
    df = market_service.get_market_sentiment(list(dates))
    if df.empty or '日期' not in df.columns:
        return pd.DataFrame()
    
    df['日期'] = df['日期'].astype(str)
    return df.sort_values('日期').reset_index(drop=True)


def calc_rolling_percentile(s: pd.Series, window: int) -> pd.Series:
    """计算滚动百分位 (0-100)"""
    return s.rolling(window, min_periods=1).apply(
        lambda x: (x <= x.iloc[-1]).sum() / len(x) * 100, raw=False
    ).fillna(50)


def calc_sentiment_score(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """计算指定前缀的情绪综合分"""
    cols = [f'{prefix}_{c}' for c in SENTIMENT_COLS if f'{prefix}_{c}' in df.columns]
    if not cols:
        return df
    
    # 竞价使用固定窗口BID_WINDOW，收盘使用动态窗口
    if prefix == '竞价':
        window = BID_WINDOW
    else:
        window = max(3, min(10, len(df) // 2))
    
    score_name = f'{prefix}情绪综合分' if prefix == '竞价' else '情绪综合分'
    interval_name = f'{prefix}情绪区间' if prefix == '竞价' else '情绪区间'
    
    pct_cols = []
    for col in cols:
        is_reverse = any(r in col for r in REVERSE_COLS)
        pct = calc_rolling_percentile(df[col], window)
        pct_col = f'{col}_pct'
        df[pct_col] = 100 - pct if is_reverse else pct
        pct_cols.append(pct_col)
    
    df[score_name] = df[pct_cols].mean(axis=1)
    df[interval_name] = pd.cut(
        df[score_name], 
        bins=[0, 20, 40, 60, 80, 100],
        labels=['冰点', '偏冷', '中性', '偏暖', '过热'],
        right=True
    )
    return df


def process_data(df: pd.DataFrame) -> pd.DataFrame:
    """处理数据：计算情绪分"""
    df = df.copy()
    for prefix in ['收盘', '竞价']:
        df = calc_sentiment_score(df, prefix)
    return df


def add_dynamic_threshold(df: pd.DataFrame, vol_col: str = '收盘_上证涨跌幅') -> pd.DataFrame:
    """
    添加动态阈值和动态情绪区间
    
    Args:
        df: 包含情绪综合分的数据框
        vol_col: 波动率计算列名
    
    Returns:
        添加了动态阈值相关列的数据框
    """
    if df.empty or '情绪综合分' not in df.columns:
        return df
    
    df = df.copy()
    
    if vol_col not in df.columns:
        df['动态阈值'] = [BASE_THRESHOLDS] * len(df)
        return df
    
    try:
        # 计算波动率
        df['波动率'] = df[vol_col].rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std()
        
        # 计算波动率百分位
        df['波动率百分位'] = df['波动率'].expanding().apply(
            lambda x: (x <= x[-1]).sum() / len(x) * 100, raw=True
        )
        
        def get_dynamic_thresholds(vol_pct: float) -> List[float]:
            """根据波动率百分位计算动态阈值"""
            if pd.isna(vol_pct):
                return BASE_THRESHOLDS
            offset = (vol_pct - 50) / 50 * ADJUST_FACTOR
            return sorted(max(0, min(100, t + offset)) for t in BASE_THRESHOLDS)
        
        df['动态阈值'] = df['波动率百分位'].apply(get_dynamic_thresholds)
        
    except Exception as e:
        st.warning(f"计算动态阈值时出错: {str(e)}")
        df['动态阈值'] = [BASE_THRESHOLDS] * len(df)
    
    return df


def add_bid_evolution_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    添加竞价演化分析数据
    
    注意：竞价情绪分只使用'竞价_全场涨跌比'一个指标，
    与收盘情绪综合分（多指标加权）不同
    
    Args:
        df: 包含情绪综合分的数据框
    
    Returns:
        添加了竞价演化相关列的数据框
    """
    if df.empty or '情绪综合分' not in df.columns:
        return df
    
    df = df.copy()
    
    try:
        # 竞价情绪分：只用竞价_全场涨跌比的滚动百分位
        if '竞价_全场涨跌比' in df.columns:
            df['竞价情绪分'] = calc_rolling_percentile(df['竞价_全场涨跌比'], BID_WINDOW)
        
        # 计算昨日情绪分
        df['昨日情绪分'] = df['情绪综合分'].shift(1)
        df['昨日区间'] = df['情绪区间'].shift(1)
        
        # 计算情绪变化
        if '竞价情绪分' in df.columns:
            df['情绪变化'] = df['竞价情绪分'] - df['昨日情绪分']
        
    except Exception as e:
        st.warning(f"计算竞价演化数据时出错: {str(e)}")
    
    return df


# ==================== 图表 ====================
def create_sentiment_chart(df: pd.DataFrame) -> go.Figure:
    """创建情绪综合分趋势图"""
    fig = go.Figure()
    
    # 竞价情绪分（始终显示）
    if '竞价情绪综合分' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df['竞价情绪综合分'],
            name='竞价情绪分', mode='lines+markers',
            line=dict(color='#ff7f0e', width=2, dash='dash'),
            marker=dict(size=6)
        ))
    
    # 收盘情绪分（仅显示有收盘数据的日期）
    df_sp = df.dropna(subset=['收盘_总额', '收盘_全场涨跌比'], how='all')
    if '情绪综合分' in df_sp.columns and not df_sp.empty:
        fig.add_trace(go.Scatter(
            x=df_sp['日期'], y=df_sp['情绪综合分'],
            name='收盘情绪分', mode='lines+markers',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=8)
        ))
    
    # 添加情绪区间背景
    for y0, y1, color, name in ZONES:
        fig.add_hrect(
            y0=y0, y1=y1, fillcolor=color, opacity=0.1, line_width=0,
            annotation_text=name, annotation_position='right'
        )
    
    fig.update_layout(
        height=400,
        template='plotly_white',
        hovermode='x unified',
        margin=dict(l=50, r=80, t=40, b=80),
        yaxis=dict(range=[0, 100], title='情绪综合分'),
        xaxis=dict(type='category', tickangle=-45),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )
    return fig


def create_bid_evolution_chart_with_threshold(df: pd.DataFrame) -> go.Figure:
    """
    创建竞价情绪 vs 昨日收盘情绪图表（含动态阈值）
    
    Args:
        df: 包含情绪数据和动态阈值的数据框
    
    Returns:
        Plotly Figure 对象
    """
    fig = go.Figure()
    
    # 添加昨日收盘情绪分
    if '昨日情绪分' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df['昨日情绪分'],
            name='昨日收盘情绪分', mode='lines+markers',
            line=dict(color=COLORS['line_blue'], width=2),
            marker=dict(size=6)
        ))
    
    # 添加今日竞价情绪分
    if '竞价情绪分' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df['竞价情绪分'],
            name='今日竞价情绪分', mode='lines+markers',
            line=dict(color=COLORS['line_orange'], width=2),
            marker=dict(size=6)
        ))
    
    # 添加动态阈值线
    if '动态阈值' in df.columns:
        # 提取动态阈值的各个边界
        df['动态冰点上界'] = df['动态阈值'].apply(lambda x: x[0] if isinstance(x, list) else 20)
        df['动态偏冷上界'] = df['动态阈值'].apply(lambda x: x[1] if isinstance(x, list) else 40)
        df['动态中性上界'] = df['动态阈值'].apply(lambda x: x[2] if isinstance(x, list) else 60)
        df['动态偏暖上界'] = df['动态阈值'].apply(lambda x: x[3] if isinstance(x, list) else 80)
        
        # 添加动态阈值线（使用点状虚线，半透明）
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df['动态冰点上界'],
            name='动态冰点线', line=dict(color=COLORS['冰点'], width=2, dash='dot'),
            mode='lines', opacity=0.7, showlegend=True
        ))
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df['动态偏冷上界'],
            name='动态偏冷线', line=dict(color=COLORS['偏冷'], width=2, dash='dot'),
            mode='lines', opacity=0.7, showlegend=True
        ))
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df['动态中性上界'],
            name='动态中性线', line=dict(color=COLORS['中性'], width=2, dash='dot'),
            mode='lines', opacity=0.7, showlegend=True
        ))
        fig.add_trace(go.Scatter(
            x=df['日期'], y=df['动态偏暖上界'],
            name='动态偏暖线', line=dict(color=COLORS['偏暖'], width=2, dash='dot'),
            mode='lines', opacity=0.7, showlegend=True
        ))
    
    # 添加固定阈值线作为参考（更淡的颜色）
    for th in BASE_THRESHOLDS:
        fig.add_hline(y=th, line_dash='dash', line_color='lightgray', 
                     line_width=0.8, opacity=0.4)
    
    fig.update_layout(
        height=450,
        template='plotly_white',
        hovermode='x unified',
        margin=dict(l=50, r=20, t=40, b=80),
        yaxis=dict(range=[0, 100], title='情绪分'),
        xaxis=dict(type='category', tickangle=-45),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )
    
    return fig


# ==================== 指标卡片 ====================
def render_metric_card(col, title: str, value, delta=None, suffix: str = ""):
    """渲染指标卡片"""
    with col:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            st.metric(title, "--", suffix)
        else:
            st.metric(title, f"{value:.1f}" if isinstance(value, float) else str(value), 
                     f"{delta:+.1f}" if delta is not None else suffix)


def render_metrics(today: pd.Series, yesterday: pd.Series, has_sp: bool):
    """渲染四个指标卡片"""
    cols = st.columns(4)
    
    # 收盘情绪分
    sp_value = today.get('情绪综合分') if has_sp else None
    sp_delta = (today.get('情绪综合分') - yesterday.get('情绪综合分')) if has_sp and pd.notna(yesterday.get('情绪综合分')) else None
    sp_suffix = str(today.get('情绪区间', '-')) if has_sp else "待更新"
    render_metric_card(cols[0], "🎯 收盘情绪分", sp_value, sp_delta, sp_suffix)
    
    # 竞价情绪分
    jj_value = today.get('竞价情绪综合分')
    jj_delta = (today.get('竞价情绪综合分') - yesterday.get('竞价情绪综合分')) if pd.notna(yesterday.get('竞价情绪综合分')) else None
    render_metric_card(cols[1], "� 竞价情绪分", jj_value, jj_delta, str(today.get('竞价情绪区间', '-')))
    
    # 收盘日变化
    render_metric_card(cols[2], "📈 收盘日变化", sp_delta)
    
    # 竞价日变化
    render_metric_card(cols[3], "📈 竞价日变化", jj_delta)


# ==================== 主函数 ====================
def render_sentiment_analysis_deep():
    """渲染情绪深度分析页面"""
    st.markdown("### 🔬 情绪数据深度分析")
    
    # 加载数据
    df = load_data()
    if df.empty:
        st.warning("⚠️ 暂无情绪数据")
        return
    
    # 处理数据
    df = process_data(df)
    df = add_dynamic_threshold(df)  # 添加动态阈值
    df = add_bid_evolution_data(df)  # 添加竞价演化数据
    df_sorted = df.sort_values('日期', ascending=False).reset_index(drop=True)
    
    # 获取今天和昨天数据
    today = df.iloc[-1]
    yesterday = df.iloc[-2] if len(df) > 1 else today
    has_sp_today = pd.notna(today.get('收盘_总额')) or pd.notna(today.get('收盘_全场涨跌比'))
    
    # 标题和提示
    st.caption(f"📊 {df_sorted['日期'].iloc[-1]} ~ {df_sorted['日期'].iloc[0]}（共{len(df_sorted)}天）")
    if not has_sp_today:
        st.caption("⚠️ 今日收盘数据尚未更新")
    st.markdown("---")
    
    # 指标卡片
    render_metrics(today, yesterday, has_sp_today)
    
    st.markdown("---")
    
    # 趋势图
    fig = create_sentiment_chart(df)
    st.plotly_chart(fig, width='stretch')
    
    st.markdown("---")
    
    # 竞价情绪 vs 昨日收盘情绪（含动态阈值）
    st.markdown("#### 🔄 竞价情绪 vs 昨日收盘情绪（含动态阈值）")
    fig2 = create_bid_evolution_chart_with_threshold(df)
    st.plotly_chart(fig2, use_container_width=True)
    
    # 添加分析说明
    if '昨日情绪分' in df.columns and '竞价情绪分' in df.columns:
        with st.expander("📊 竞价情绪分析"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("昨日收盘情绪", f"{today['昨日情绪分']:.1f}", 
                         str(today.get('昨日区间', '-')))
            with col2:
                st.metric("今日竞价情绪", f"{today['竞价情绪分']:.1f}")
            with col3:
                change = today['竞价情绪分'] - today['昨日情绪分']
                change_text = f"{change:+.1f}"
                if change > 10:
                    status = "大幅增强"
                elif change < -10:
                    status = "大幅减弱"
                else:
                    status = "平稳"
                st.metric("情绪变化", change_text, status)
    
    # 数据表格
    st.markdown("---")
    st.markdown("##### 📋 完整数据")
    st.dataframe(df_sorted, hide_index=True, width='stretch')


if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="情绪深度分析")
    render_sentiment_analysis_deep()
