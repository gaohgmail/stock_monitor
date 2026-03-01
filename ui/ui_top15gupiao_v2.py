# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd

# ========== 1. 私有配置与辅助组件 ==========

COL_AMOUNT = "金额"
COL_PCT_CHG = "涨跌幅"

COUNT_COLORS = {
    'count_gt_10': '#ff9696',
    'count_gt_5': '#ffc8d2',
    'count_gt_3': '#ffffb4',
    'count_default': '#ffffff',
}

def _get_count_color(count):
    try:
        count = int(count) if isinstance(count, (int, float)) else 0
    except:
        count = 0
    
    if count > 10:
        return COUNT_COLORS['count_gt_10']
    elif count > 5:
        return COUNT_COLORS['count_gt_5']
    elif count > 3:
        return COUNT_COLORS['count_gt_3']
    else:
        return COUNT_COLORS['count_default']

def _style_dataframe(df, col_amount='金额'):
    """根据出现次数设置行的背景色"""
    if df.empty:
        return df
    
    if '出现次数' not in df.columns:
        return df.style.format({col_amount: "{:.2f}亿", "涨跌幅": "{:+.2f}%"})
    
    def style_row(row):
        color = _get_count_color(row.get('出现次数', 0))
        return [f'background-color: {color}' for _ in row]
    
    styler = df.style
    styler = styler.apply(style_row, axis=1)
    styler = styler.format({col_amount: "{:.2f}亿", "涨跌幅": "{:+.2f}%"})
    
    return styler

def _render_metric_row(auc_data, cls_data):
    def get_stats(df):
        if df.empty: return 0.0, 0.0
        total = df[COL_AMOUNT].sum() / 1e8 if COL_AMOUNT in df.columns else 0
        avg_chg = df[COL_PCT_CHG].mean() if COL_PCT_CHG in df.columns else 0
        return total, avg_chg

    auc_total, auc_chg = get_stats(auc_data)
    cls_total, cls_chg = get_stats(cls_data)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("💰 竞价Top15总额", f"{auc_total:.2f}亿")
    m2.metric("📊 竞价平均成交额", f"{auc_total/15:.2f}亿" if auc_total > 0 else "0.00亿")
    m3.metric("📈 竞价平均涨幅", f"{auc_chg:.2f}%")
    m4.metric("💰 收盘Top15总额", f"{cls_total:.2f}亿")
    m5.metric("📊 收盘平均成交额", f"{cls_total/15:.2f}亿" if cls_total > 0 else "0.00亿")
    m6.metric("📈 收盘平均涨幅", f"{cls_chg:.2f}%")

def _render_detail_tables(df_auc, df_cls):
    column_config = {}
    if COL_AMOUNT in df_auc.columns or COL_AMOUNT in df_cls.columns:
        column_config[COL_AMOUNT] = st.column_config.NumberColumn("金额", format="%.2f亿")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**🔴 竞价成交 Top 15**")
        if not df_auc.empty:
            df_auc_display = df_auc.copy()
            if COL_AMOUNT in df_auc_display.columns:
                df_auc_display[COL_AMOUNT] = df_auc_display[COL_AMOUNT] / 1e8
            styler = _style_dataframe(df_auc_display, COL_AMOUNT)
            st.dataframe(styler, hide_index=True, height=570)
        else:
            st.info("暂无竞价数据")
    with c2:
        st.markdown("**🔵 收盘成交 Top 15**")
        if not df_cls.empty:
            df_cls_display = df_cls.copy()
            if COL_AMOUNT in df_cls_display.columns:
                df_cls_display[COL_AMOUNT] = df_cls_display[COL_AMOUNT] / 1e8
            styler = _style_dataframe(df_cls_display, COL_AMOUNT)
            st.dataframe(styler, hide_index=True, height=570)
        else:
            st.info("暂无收盘数据")

def render_top15_dashboard(df_auc: pd.DataFrame, df_cls: pd.DataFrame, target_date=None):
    if target_date:
        date_str = target_date.strftime('%Y-%m-%d') if hasattr(target_date, 'strftime') else str(target_date)
        st.caption(f"📅 日期: {date_str}")
    st.markdown("---")

    st.markdown("##### 🎯 核心情绪指标")
    _render_metric_row(df_auc, df_cls)
    
    st.markdown("---")

    st.markdown("##### 📋 明细数据")
    _render_detail_tables(df_auc, df_cls)
