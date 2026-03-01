# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from tools.config import COL
from tools.data_loader import load_concept_data
from collections import Counter
from datetime import datetime

CONCEPT_BLACKLIST = {'深股通', '沪股通', '融资融券', '转融券标的', '标普道琼斯A股', 'MSCIA股'}

def _get_code_col(df):
    for col in [COL.CODE, '股票代码', 'code']:
        if col in df.columns:
            return col
    return None

def enrich_concept(df_zt, trade_date=None):
    if df_zt.empty:
        return df_zt
    if trade_date is None:
        trade_date = datetime.now()
    df_concept = load_concept_data(trade_date)
    if df_concept.empty:
        return df_zt
    code_col = _get_code_col(df_zt)
    if not code_col:
        return df_zt
    merge_cols = [COL.CODE, COL.CONCEPT, COL.INDUSTRY]
    reason_cols = ['历史涨停原因类别', '涨停原因类别']
    for rc in reason_cols:
        if rc in df_concept.columns and rc not in merge_cols:
            merge_cols.append(rc)
    df_merged = df_zt.merge(df_concept[merge_cols], on=COL.CODE, how='left')
    if COL.CONCEPT in df_merged.columns:
        df_merged['热点概念'] = df_merged[COL.CONCEPT]
    if COL.INDUSTRY in df_merged.columns:
        df_merged['所属行业'] = df_merged[COL.INDUSTRY]
    reason_cols = ['历史涨停原因类别', '涨停原因类别']
    for rc in reason_cols:
        if rc in df_merged.columns:
            df_merged['涨停原因'] = df_merged[rc]
            break
    return df_merged

def _dist_concept(df):
    if df.empty or '热点概念' not in df.columns:
        return {}
    concept_list = [c.strip() for concepts in df['热点概念'].fillna('') for c in str(concepts).split(';') if c.strip() and c.strip() not in CONCEPT_BLACKLIST and len(c.strip()) >= 2]
    return dict(Counter(concept_list).most_common(10))

def _dist_industry(df):
    if df.empty or '所属行业' not in df.columns:
        return {}
    return dict(df['所属行业'].fillna('').value_counts().head(10))

def _dist_reason(df):
    if df.empty:
        return pd.DataFrame()
    reason_col = None
    for col in ['历史涨停原因类别', '涨停原因类别']:
        if col in df.columns:
            reason_col = col
            break
    if not reason_col:
        return pd.DataFrame()
    reason_list = [r.strip() for reasons in df[reason_col].fillna('') for r in str(reasons).split('+') if r.strip() and len(r.strip()) >= 2]
    if not reason_list:
        return pd.DataFrame()
    df_reason = pd.DataFrame(Counter(reason_list).most_common(20), columns=['涨停原因', '出现次数'])
    return df_reason

def analyze_zhangting_stats(df):
    if df.empty:
        return {'count': 0, 'avg_amount': 0, 'max_board': 0, 'leader': '--', 'board_map': {}}
    stats = {'count': len(df), 'avg_amount': (df[COL.STD_AMOUNT].mean() / 1e8) if COL.STD_AMOUNT in df.columns else 0}
    if COL.CONSECUTIVE_LIMIT_UP_DAYS in df.columns:
        stats['max_board'] = int(df[COL.CONSECUTIVE_LIMIT_UP_DAYS].max())
        leaders = df[df[COL.CONSECUTIVE_LIMIT_UP_DAYS] == stats['max_board']][COL.NAME].tolist()
        stats['leader'] = leaders[0] if leaders else "--"
        vc = df[COL.CONSECUTIVE_LIMIT_UP_DAYS].value_counts()
        stats['board_map'] = {'首板': int(vc.get(1, 0)), '2板': int(vc.get(2, 0)), '3板': int(vc.get(3, 0)), '4板': int(vc.get(4, 0)), '5板+': int(vc[vc.index >= 5].sum())}
    else:
        stats.update({'max_board': 1, 'leader': '--', 'board_map': {'首板': len(df)}})
    return stats

def _render_metrics(stats):
    cols = st.columns(6)
    bm = stats.get('board_map', {})
    metrics = [("📈 涨停家数", f"{stats['count']}", None), ("💰 平均成交", f"{stats['avg_amount']:.2f}亿", None), ("🚀 最高板", f"{stats['max_board']}板", stats['leader']), ("⭐ 首板", f"{bm.get('首板', 0)}", None), ("⭐⭐ 2板", f"{bm.get('2板', 0)}", None), ("🔥 高板(3+)", f"{bm.get('3板',0) + bm.get('4板',0) + bm.get('5板+',0)}", None)]
    for col, (label, value, delta) in zip(cols, metrics):
        col.metric(label, value, delta=delta, delta_color="normal" if delta else "off")

def _render_bar_chart(board_map):
    if not board_map:
        return
    categories = list(board_map.keys())
    values = list(board_map.values())
    colors = ['#C8E6C9', '#81C784', '#FFB74D', '#FF8A65', '#E57373']
    fig = go.Figure(go.Bar(x=categories, y=values, text=[f"<b>{v}</b>" for v in values], textposition='inside', marker_color=colors[:len(categories)], hovertemplate="板次: %{x}<br>家数: %{y}<extra></extra>"))
    fig.update_layout(height=300, template="plotly_white", margin=dict(l=10, r=10, t=30, b=10), yaxis=dict(title="家数", showgrid=True, gridcolor='#F0F2F6'), xaxis=dict(title=None))
    st.plotly_chart(fig)

def render_zhangting_dashboard(df_zt, stats, target_date=None, stage="收盘", show_concept=False):
    if df_zt.empty:
        st.info("💡 该交易日暂无符合条件的涨停数据")
        return
    pct_col = "竞价涨幅" if stage == "竞价" else "收盘涨幅"
    st.markdown("##### 🎯 市场情绪脉搏")
    _render_metrics(stats)
    col_chart, col_info = st.columns([2, 1])
    with col_chart:
        st.markdown("##### 📊 连板梯队分布")
        _render_bar_chart(stats.get('board_map'))
    with col_info:
        st.markdown("##### 💡 盘面观察")
        if stats['max_board'] >= 5:
            st.markdown(f"""<div style="background-color: #fffbe6; border-left: 4px solid #faad14; padding: 10px; border-radius: 4px; margin: 5px 0;">核心龙头 <span style="color: #eb2f96; font-weight: bold; font-size: 16px;">【{stats['leader']}】</span> 已突破至 <span style="color: #ff4d4f; font-weight: bold; font-size: 16px;"> {stats['max_board']} </span>板，关注抱团释放。</div>""", unsafe_allow_html=True)
        elif stats['max_board'] >= 3:
            st.markdown(f"""<div style="background-color: #fffbe6; border-left: 4px solid #faad14; padding: 10px; border-radius: 4px; margin: 5px 0;">空间板处于 <span style="color: #ff4d4f; font-weight: bold; font-size: 16px;"> {stats['max_board']} </span>板，市场进入中位竞争阶段。</div>""", unsafe_allow_html=True)
        else:
            st.info("市场以首板和二板为主，处在试错期或混沌期。")
        if pct_col in df_zt.columns:
            high_pct = df_zt[df_zt[pct_col] >= 19]
            if not high_pct.empty:
                names = " | ".join(high_pct[COL.NAME].tolist())
                st.markdown(f"""<div style="background-color: #fff2e6; border: 2px solid #ff7a45; border-radius: 8px; padding: 12px; margin-top: 10px;"><b>🔥 涨幅超19%涨停股 ({len(high_pct)}只)</b><br><span>{names}</span></div>""", unsafe_allow_html=True)
    
    # 截断左右分栏，后续内容占满全宽
    st.write("")
    st.markdown("---")
    st.markdown("##### 📋 涨停梯队明细")
    
    # 先富集概念数据，获取涨停原因
    df_show = df_zt.copy()
    if target_date is not None:
        df_enriched = enrich_concept(df_zt, target_date)
        if '涨停原因' in df_enriched.columns:
            df_show = df_show.merge(df_enriched[[COL.CODE, '涨停原因']], on=COL.CODE, how='left')
    
    if COL.STD_AMOUNT in df_show.columns:
        df_show[COL.STD_AMOUNT] = df_show[COL.STD_AMOUNT] / 1e8
    
    display_cols = [COL.NAME, COL.CONSECUTIVE_LIMIT_UP_DAYS, pct_col, COL.LOCK_AMOUNT, COL.STD_AMOUNT]
    if '涨停原因' in df_show.columns:
        display_cols.append('涨停原因')
    
    valid_display = [c for c in display_cols if c in df_show.columns]
    
    col_config = {COL.NAME: st.column_config.TextColumn("名称", width="small"), 
                  COL.CONSECUTIVE_LIMIT_UP_DAYS: st.column_config.NumberColumn("连板", format="%d 🔥"), 
                  pct_col: st.column_config.NumberColumn("涨幅", format="%.2f%%"), 
                  COL.LOCK_AMOUNT: st.column_config.NumberColumn("封单(亿)", format="%.2f"), 
                  COL.STD_AMOUNT: st.column_config.NumberColumn("成交额(亿)", format="%.2f"),
                  '涨停原因': st.column_config.TextColumn("涨停原因", width="large")}
    
    sort_by = [c for c in [COL.CONSECUTIVE_LIMIT_UP_DAYS, COL.LOCK_AMOUNT] if c in df_show.columns]
    st.dataframe(df_show[valid_display].sort_values(sort_by, ascending=False) if sort_by else df_show[valid_display], column_config=col_config, hide_index=True, height=500)
    
    if stage == "收盘" and show_concept:
        render_concept_analysis_tables(df_zt, target_date)


def render_concept_analysis_tables(df_zt, target_date):
    """渲染概念分析表格（热门概念、热门行业、涨停原因分析）"""
    df_enriched = enrich_concept(df_zt, target_date)
    c1, c2, c3 = st.columns(3)
    concept_dist = _dist_concept(df_enriched)
    industry_dist = _dist_industry(df_enriched)
    reason_df = _dist_reason(df_enriched)
    with c1:
        st.markdown("##### 🔥 热门概念 TOP 10")
        if concept_dist:
            st.dataframe(pd.DataFrame(list(concept_dist.items()), columns=['概念', '涨停数']), hide_index=True, height=400)
        else:
            st.info("暂无概念数据")
    with c2:
        st.markdown("##### 🏭 热门行业 TOP 10")
        if industry_dist:
            st.dataframe(pd.DataFrame(list(industry_dist.items()), columns=['行业', '涨停数']), hide_index=True, height=400)
        else:
            st.info("暂无行业数据")
    with c3:
        st.markdown("##### 📊 涨停原因分析")
        if not reason_df.empty:
            st.dataframe(reason_df, hide_index=True, height=400)
        else:
            st.info("暂无原因数据")
