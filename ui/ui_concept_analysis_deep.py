# -*- coding: utf-8 -*-
# ui/ui_concept_analysis_deep.py
# 题材深度分析页面 - 搜索 + 历史表格 + 多日图表

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

from tools.config import COL
from core.service_layer import market_service, DataStatus
from ui.ui_concepts import (
    COLUMNS,
    COLUMN_LABELS,
    STRONG_CONCEPT_CONDITIONS,
    _standardize_column_names,
    _find_column,
    _create_mini_bar_chart,
    _precompute_column_indices,
    highlight_concepts
)


@st.cache_data(ttl=3600)
def _load_all_concepts(target_date: datetime) -> list:
    """加载所有题材名称用于搜索"""
    concepts = []
    for stage in ["竞价", "收盘"]:
        res_stats, _ = market_service.get_concept_data(target_date, data_type=stage)
        if res_stats.status == DataStatus.OK and not res_stats.data.empty:
            name_col = _find_column(res_stats.data, "concept_name")
            if name_col:
                concepts.extend(res_stats.data[name_col].tolist())
    return list(set(concepts))


@st.cache_data(ttl=3600)
def _load_concept_history(concept_name: str, days: int, target_date: datetime, stage: str = "竞价") -> pd.DataFrame:
    """加载题材历史数据"""
    history_data = []
    
    for i in range(days):
        check_date = target_date - timedelta(days=i)
        date_str = check_date.strftime('%Y-%m-%d')
        
        res_stats, res_details = market_service.get_concept_data(check_date, data_type=stage)
        
        if res_stats.status == DataStatus.OK and not res_stats.data.empty:
            df = res_stats.data
            df = _standardize_column_names(df)
            
            name_col = _find_column(df, "concept_name")
            
            if name_col:
                mask = df[name_col].astype(str) == concept_name
                if mask.any():
                    row = df[mask].iloc[0].to_dict()
                    row['日期'] = date_str
                    row['阶段'] = stage
                    history_data.append(row)
    
    if not history_data:
        return pd.DataFrame()
    
    df = pd.DataFrame(history_data)
    df = df.sort_values('日期', ascending=True)
    return df


def _add_bar_trace(
    fig, 
    x, 
    y, 
    color, 
    text, 
    customdata, 
    hover_label, 
    row, 
    col, 
    secondary_y=False,
    opacity=1.0
):
    """添加柱状图追踪（辅助函数，减少重复代码）"""
    fig.add_trace(
        go.Bar(
            x=x, y=y,
            marker_color=color,
            opacity=opacity,
            text=text,
            textposition='inside',
            textfont=dict(size=12, color="white", weight="bold"),
            showlegend=False,
            customdata=customdata,
            hovertemplate=(
                f"<b>日期</b>: %{{customdata}}<br>"
                f"<b>{hover_label}</b>: %{{y}}<br>"
                "<extra></extra>"
            )
        ),
        row=row, col=col,
        secondary_y=secondary_y
    )


def _add_scatter_trace(
    fig, 
    x, 
    y, 
    color, 
    customdata, 
    hover_label, 
    row, 
    col, 
    secondary_y=False
):
    """添加散点图追踪（辅助函数，减少重复代码）"""
    fig.add_trace(
        go.Scatter(
            x=x, y=y,
            line=dict(color=color, width=2),
            mode='lines+markers',
            showlegend=False,
            customdata=customdata,
            hovertemplate=(
                f"<b>日期</b>: %{{customdata}}<br>"
                f"<b>{hover_label}</b>: %{{y:.2f}}%<br>"
                "<extra></extra>"
            )
        ),
        row=row, col=col,
        secondary_y=secondary_y
    )


def _render_multi_charts(df: pd.DataFrame):
    """渲染多维度图表（共享X轴垂直布局）"""
    if df.empty:
        return
    
    date_col = _find_column(df, "date")
    
    if not date_col or date_col not in df.columns:
        st.warning("未找到日期列")
        return
    
    x_indices = list(range(len(df)))
    date_labels = [str(d)[-5:] for d in df[date_col].tolist()]
    full_date_labels = [str(d) for d in df[date_col].tolist()]
    
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        specs=[
            [{}],
            [{}],
            [{}],
            [{"secondary_y": True}]
        ]
    )
    
    avg_col = _find_column(df, "avg_change")
    if avg_col and avg_col in df.columns:
        y = pd.to_numeric(df[avg_col], errors='coerce').fillna(0).tolist()
        colors = ["#d62728" if v > 0 else "#2ca02c" for v in y]
        _add_bar_trace(
            fig, x_indices, y, colors, [f"{v:.1f}" for v in y],
            full_date_labels, "涨幅", 1, 1
        )
        fig.update_yaxes(title_text="涨幅%", row=1, col=1, title_standoff=5)
    
    amount_col = _find_column(df, "amount")
    if amount_col and amount_col in df.columns:
        y = pd.to_numeric(df[amount_col], errors='coerce').fillna(0).tolist()
        _add_bar_trace(
            fig, x_indices, y, "#4facfe", [f"{v:.1f}" for v in y],
            full_date_labels, "成交额", 2, 1
        )
        fig.update_yaxes(title_text="成交额(亿)", row=2, col=1, title_standoff=5)
    
    red_col = _find_column(df, "red_rate")
    if red_col and red_col in df.columns:
        y = pd.to_numeric(df[red_col], errors='coerce').fillna(0).tolist()
        _add_bar_trace(
            fig, x_indices, y, "#9c27b0", [f"{v:.1f}" for v in y],
            full_date_labels, "红盘率", 3, 1
        )
        fig.update_yaxes(title_text="红盘率%", row=3, col=1, title_standoff=5)
    
    zt_col = _find_column(df, "limit_up_count")
    dt_col = _find_column(df, "limit_down_count")
    up_col = _find_column(df, "big_up_rate")
    down_col = _find_column(df, "big_down_rate")
    
    if zt_col and zt_col in df.columns:
        y_zt = pd.to_numeric(df[zt_col], errors='coerce').fillna(0).tolist()
        _add_bar_trace(
            fig, x_indices, y_zt, "#d62728",
            [f"{int(v)}" if v > 0 else "" for v in y_zt],
            full_date_labels, "涨停", 4, 1, secondary_y=False, opacity=0.8
        )
    
    if dt_col and dt_col in df.columns:
        y_dt = pd.to_numeric(df[dt_col], errors='coerce').fillna(0).tolist()
        _add_bar_trace(
            fig, x_indices, y_dt, "#2ca02c",
            [f"{int(v)}" if v > 0 else "" for v in y_dt],
            full_date_labels, "跌停", 4, 1, secondary_y=False, opacity=0.8
        )
    
    if up_col and up_col in df.columns:
        y_up = pd.to_numeric(df[up_col], errors='coerce').fillna(0).tolist()
        _add_scatter_trace(
            fig, x_indices, y_up, "#ff4d4f",
            full_date_labels, "大涨率", 4, 1, secondary_y=True
        )
    
    if down_col and down_col in df.columns:
        y_down = pd.to_numeric(df[down_col], errors='coerce').fillna(0).tolist()
        _add_scatter_trace(
            fig, x_indices, y_down, "#2ecc71",
            full_date_labels, "大跌率", 4, 1, secondary_y=True
        )
    
    if zt_col or dt_col:
        fig.update_yaxes(title_text="涨跌停数(柱)", row=4, col=1, secondary_y=False, title_standoff=5)
    if up_col or down_col:
        fig.update_yaxes(title_text="大涨大跌率%(线)", row=4, col=1, secondary_y=True, title_standoff=5)
    
    fig.update_layout(
        hovermode='x unified',
        height=800,
        template="plotly_white",
        showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(family="Microsoft YaHei, SimHei, Arial, sans-serif")
    )
    
    fig.update_xaxes(
        showspikes=True,
        spikemode='across',
        spikethickness=1,
        spikecolor="#999999",
        spikedash="dash",
        showgrid=False
    )
    
    fig.update_xaxes(
        tickmode='array',
        tickvals=x_indices,
        ticktext=date_labels,
        tickangle=-45,
        row=4, col=1
    )
    
    for row_num in [1, 2, 3]:
        fig.update_xaxes(showticklabels=False, row=row_num, col=1)
    
    st.plotly_chart(fig, width='stretch')


def _show_history_table_popup(df: pd.DataFrame, title: str):
    """显示历史表格弹窗"""
    @st.dialog(title, width="large")
    def popup():
        _render_history_table(df)
    popup()


def _render_history_table(df: pd.DataFrame):
    """渲染历史表格（带强题材高亮和完整格式化）"""
    if df.empty:
        st.info("暂无历史数据")
        return
    
    name_col = _find_column(df, "concept_name")
    date_col = _find_column(df, "date")
    stage_col = _find_column(df, "stage")
    
    column_labels = COLUMN_LABELS
    
    preferred_cols = []
    if date_col:
        preferred_cols.append(date_col)
    
    core_order = ['stocks_count', 'increment', 'avg_change', 'red_rate', 
                  'limit_up_count', 'limit_up_rate', 'big_up_rate', 'big_down_rate', 
                  'limit_down_rate', 'limit_down_count', 'amount', 'leader']
    
    for col in core_order:
        if col in df.columns:
            preferred_cols.append(col)
    
    for col in ['continuous_limit_up_count', 'first_limit_up_count', 'blow_up_count', 'big_up_count', 'big_down_count']:
        if col in df.columns:
            preferred_cols.append(col)
    
    display_cols = preferred_cols.copy()
    for col in df.columns:
        if col != 'index' and col not in display_cols:
            display_cols.append(col)
    
    df_display = df[display_cols].copy()
    
    col_indices = _precompute_column_indices(df_display)
    styler = df_display.style
    styler = styler.apply(highlight_concepts, axis=1, col_indices=col_indices)
    
    format_dict = {}
    for col in df_display.columns:
        if col in ['stocks_count', 'limit_up_count', 'continuous_limit_up_count', 
                  'first_limit_up_count', 'blow_up_count', 'limit_down_count', 
                  'big_up_count', 'big_down_count']:
            if pd.api.types.is_numeric_dtype(df_display[col]):
                format_dict[col] = '{:.0f}'
        elif 'rate' in col or '%' in column_labels.get(col, ''):
            if pd.api.types.is_numeric_dtype(df_display[col]):
                format_dict[col] = '{:.2f}'
        elif 'increment' in col or 'amount' in col or '亿' in column_labels.get(col, ''):
            if pd.api.types.is_numeric_dtype(df_display[col]):
                format_dict[col] = '{:.2f}'
    styler = styler.format(format_dict, na_rep="-")
    
    col_config = {}
    for col in df_display.columns:
        if col == 'index':
            continue
        display_name = column_labels.get(col, col)
        if col == date_col:
            col_config[col] = st.column_config.TextColumn(display_name, width="small")
        elif col == 'leader':
            col_config[col] = st.column_config.TextColumn(display_name, width="medium")
        elif '%' in display_name or 'rate' in col:
            col_config[col] = st.column_config.NumberColumn(display_name, format="%.2f", width="small")
        elif '亿' in display_name or 'increment' in col or 'amount' in col:
            col_config[col] = st.column_config.NumberColumn(display_name, format="%.2f", width="small")
        elif 'count' in col or col in ['stocks_count']:
            col_config[col] = st.column_config.NumberColumn(display_name, format="%d", width="small")
        else:
            col_config[col] = st.column_config.TextColumn(display_name, width="small")
    
    st.dataframe(
        styler,
        column_config=col_config,
        height=500,
        hide_index=True,
        width='stretch',
    )


def render_concept_analysis_deep(target_date: datetime):
    """题材深度分析页面"""
    date_str = target_date.strftime('%Y-%m-%d')
    st.caption(f"📅 日期: {date_str}")
    
    st.markdown("### 🔍 题材深度分析")
    
    all_concepts = _load_all_concepts(target_date)
    
    col1, col3, col4 = st.columns([3, 1, 1])
    
    with col1:
        selected_concept = st.selectbox(
            "🔍 选择题材", 
            options=[""] + all_concepts,
            index=0,
            key="concept_select",
            placeholder="选择或搜索题材..."
        )
    
    with col3:
        days = st.number_input("📅 天数", min_value=1, max_value=60, value=18, key="concept_days")
    
    with col4:
        search_btn = st.button("🔍 分析", type="primary", key="concept_search_btn")
    
    for key in ["concept_jj_data", "concept_sp_data", "current_concept"]:
        if key not in st.session_state:
            st.session_state[key] = None if key != "current_concept" else ""
    
    if search_btn and selected_concept:
        with st.spinner(f"加载「{selected_concept}」的历史数据..."):
            df_jj = _load_concept_history(selected_concept, days, target_date, "竞价")
            df_sp = _load_concept_history(selected_concept, days, target_date, "收盘")
            st.session_state.concept_jj_data = df_jj
            st.session_state.concept_sp_data = df_sp
            st.session_state.current_concept = selected_concept
    
    has_data = (st.session_state.concept_jj_data is not None and not st.session_state.concept_jj_data.empty) or \
               (st.session_state.concept_sp_data is not None and not st.session_state.concept_sp_data.empty)
    
    if has_data:
        st.success(f"✅ 「{st.session_state.current_concept}」历史表现")
        
        cols = st.columns(2)
        
        with cols[0]:
            st.markdown("##### 🔴 竞价")
            if st.session_state.concept_jj_data is not None and not st.session_state.concept_jj_data.empty:
                if st.button("📊 查看历史表格", key="show_jj_table", type="secondary"):
                    _show_history_table_popup(st.session_state.concept_jj_data, f"🔴 {st.session_state.current_concept} - 竞价历史表格")
                _render_multi_charts(st.session_state.concept_jj_data)
            else:
                st.info("暂无竞价数据")
        
        with cols[1]:
            st.markdown("##### 🟢 收盘")
            if st.session_state.concept_sp_data is not None and not st.session_state.concept_sp_data.empty:
                if st.button("📊 查看历史表格", key="show_sp_table", type="secondary"):
                    _show_history_table_popup(st.session_state.concept_sp_data, f"🟢 {st.session_state.current_concept} - 收盘历史表格")
                _render_multi_charts(st.session_state.concept_sp_data)
            else:
                st.info("暂无收盘数据")
        
        if st.button("✕ 清除", key="clear_history"):
            st.session_state.concept_jj_data = None
            st.session_state.concept_sp_data = None
            st.session_state.current_concept = ""
            st.rerun()
    else:
        if search_btn and selected_concept:
            st.error(f"❌ 未找到「{selected_concept}」的历史数据")
        
        if all_concepts:
            st.info(f"💡 请从上方下拉菜单选择题材（共{len(all_concepts)}个）")
        else:
            st.info("暂无题材数据")

