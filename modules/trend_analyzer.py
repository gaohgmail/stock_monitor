# modules/trend_analyzer.py
import pandas as pd
import os
import io
import streamlit as st
from datetime import datetime
import plotly.graph_objects as go
from modules.config import DATA_DIR
from modules.data_loader import get_trade_dates, read_market_data
from modules.utils import standardize_code
from modules.analyzer import build_structure_tags

def calculate_top_amount_percentage(df, type_prefix, top_n=15):
    """计算前N占比，处理 1e8 单位和 2 位小数精度"""
    amt_col = f"{type_prefix}金额"
    
    if df.empty or amt_col not in df.columns:
        return None, pd.DataFrame()
    
    # 1. 数值化转换
    df[amt_col] = pd.to_numeric(df[amt_col], errors='coerce').fillna(0)
    
    # 2. 统一转换为“亿元”单位 (1e8)
    # 根据最大值特征判定原始单位
    max_val = df[amt_col].max()
    if max_val > 10000000:     # 原始为“元” (如 1亿=100,000,000)
        df[amt_col] = df[amt_col] / 100000000
    elif max_val > 0 and max_val < 1000000:  # 原始为“万” (如 1亿=10,000)
        df[amt_col] = df[amt_col] / 10000
    
    # 3. 涨跌幅预处理
    if '涨跌幅' in df.columns:
        df['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce').fillna(0)

    total_amount = df[amt_col].sum()
    if total_amount == 0:
        return None, pd.DataFrame()

    # 4. 排序并取前15
    df_sorted = df.sort_values(by=amt_col, ascending=False).head(top_n).copy()
    
    # 5. 格式化数值精度
    df_sorted[amt_col] = df_sorted[amt_col].round(2)
    if '涨跌幅' in df_sorted.columns:
        df_sorted['涨跌幅'] = df_sorted['涨跌幅'].round(2)
    
    top_amount = df_sorted[amt_col].sum()
    # 返回占比 (0-100) 和 排序后的 DataFrame
    return (top_amount / total_amount) * 100, df_sorted
@st.cache_data
def analyze_and_plot_top_stocks_trend(today_date, num_days=30):
    """生成 Plotly 趋势图数据和今日详情"""
    all_dates = get_trade_dates(count=30) 
    recent_dates = [d for d in all_dates if d <= today_date][-num_days:]

    plot_data = []
    auction_top_codes_history = {}
    close_top_codes_history = {}
    
    current_day_auction_top = pd.DataFrame()
    current_day_close_top = pd.DataFrame()

    for d in recent_dates:
        df_auction = read_market_data(d, '竞价行情')
        df_close = read_market_data(d, '收盘行情')

        auc_p, df_auc_t = calculate_top_amount_percentage(df_auction, "竞价")
        cls_p, df_cls_t = calculate_top_amount_percentage(df_close, "收盘")

        if auc_p is not None and cls_p is not None:
            plot_data.append({'date': d, 'auc': auc_p, 'cls': cls_p})

        # 记录历史用于连续天数计算
        if not df_auc_t.empty:
            auction_top_codes_history[d] = set(df_auc_t['股票代码'].apply(standardize_code))
            if d == today_date: current_day_auction_top = df_auc_t
            
        if not df_cls_t.empty:
            close_top_codes_history[d] = set(df_cls_t['股票代码'].apply(standardize_code))
            if d == today_date: current_day_close_top = df_cls_t

    # --- Plotly 交互式制图逻辑 ---
    fig = None
    if plot_data:
        pdf = pd.DataFrame(plot_data)
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=pdf['date'], y=pdf['auc'],
            mode='lines+markers',
            name='竞价Top15占比',
            line=dict(color='#EF5350', width=3),
            marker=dict(size=8),
            hovertemplate='日期: %{x}<br>占比: %{y:.2f}%<extra></extra>'
        ))
        
        fig.add_trace(go.Scatter(
            x=pdf['date'], y=pdf['cls'],
            mode='lines+markers',
            name='收盘Top15占比',
            line=dict(color='#42A5F5', width=3),
            marker=dict(size=8),
            hovertemplate='日期: %{x}<br>占比: %{y:.2f}%<extra></extra>'
        ))

        fig.update_layout(
            title=dict(text="市场集中度趋势 (Top15成交额占比)", x=0.5),
            xaxis_title="交易日",
            yaxis_title="占比 (%)",
            yaxis=dict(ticksuffix="%"), # 修复 yaxis 属性设置方式
            hovermode="x unified",
            margin=dict(l=20, r=20, t=50, b=20),
            height=380,
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

    # 计算连续天数逻辑
    def get_count(code, history_dict):
        count = 0
        sorted_dates = sorted(history_dict.keys(), reverse=True)
        for d in sorted_dates:
            if code in history_dict[d]: count += 1
            else: break
        return count

    for df, hist in [(current_day_auction_top, auction_top_codes_history), 
                     (current_day_close_top, close_top_codes_history)]:
        if not df.empty:
            df['连续天数'] = df['股票代码'].apply(lambda x: get_count(standardize_code(x), hist))

    return fig, current_day_auction_top, current_day_close_top

def style_market_table(df, type_prefix):
    """表格美化"""
    amt_col = f"{type_prefix}金额"
    
    def color_pct(val):
        if val > 0: return 'color: #ef5350; font-weight: bold'
        if val < 0: return 'color: #66bb6a; font-weight: bold'
        return 'color: gray'

    def color_count(val):
        if val >= 5: return 'background-color: #ff4b4b; color: white'
        if val >= 3: return 'background-color: #ff8a80'
        if val >= 2: return 'background-color: #fff9c4'
        return ''

    cols = ['股票代码', '股票简称', amt_col, '涨跌幅', '连续天数', '结构标签']
    valid_cols = [c for c in cols if c in df.columns]
    
    # 注意：使用 map 代替 applymap (Pandas 2.0+ 推荐)
    styler = df[valid_cols].style
    if '涨跌幅' in valid_cols:
        styler = styler.map(color_pct, subset=['涨跌幅'])
    if '连续天数' in valid_cols:
        styler = styler.map(color_count, subset=['连续天数'])
        
    return styler.format({amt_col: "{:.2f} 亿", "涨跌幅": "{:+.2f}%"})

def display_trend_analysis(selected_date):
    """主渲染函数"""
    st.subheader(f"📊 市场集中度与个股趋势 ({selected_date.strftime('%Y-%m-%d')})")
    
    # 1. 执行计算
    fig, df_auc, df_cls = analyze_and_plot_top_stocks_trend(selected_date)
    
    # 2. 标签拼接
    all_dates = get_trade_dates(30)
    try:
        curr_idx = all_dates.index(selected_date)
        prev_date = all_dates[curr_idx - 1] if curr_idx > 0 else None
        if prev_date:
            tags_df = build_structure_tags(selected_date, prev_date)
            if not tags_df.empty:
                tags_subset = tags_df[['股票代码', '结构标签']]
                if not df_auc.empty:
                    df_auc = df_auc.merge(tags_subset, on='股票代码', how='left').fillna('')
                if not df_cls.empty:
                    df_cls = df_cls.merge(tags_subset, on='股票代码', how='left').fillna('')
    except:
        pass

    # 3. 渲染图表 (使用 plotly_chart)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    
    # 4. 渲染双栏表格
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🔴 竞价成交额 Top15")
        if not df_auc.empty:
            st.dataframe(style_market_table(df_auc, "竞价"), use_container_width=True, height=550)
        else:
            st.info("暂无数据")
            
    with col2:
        st.markdown("#### 🔵 收盘成交额 Top15")
        if not df_cls.empty:
            st.dataframe(style_market_table(df_cls, "收盘"), use_container_width=True, height=550)
        else:
            st.info("暂无数据")
