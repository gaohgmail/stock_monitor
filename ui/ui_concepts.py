# -*- coding: utf-8 -*-
# ui/ui_concepts.py
# 题材共振页面 - 表格选中弹窗下钻


import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from tools.config import COL
from core.service_layer import market_service, DataStatus


# =============================================================================
# 模块 1: 常量与配置
# =============================================================================

STRONG_CONCEPT_CONDITIONS = {
    'min_stocks': 10,
    'min_red_ratio': 75,
    'min_change': 1.2,
    'min_fund': 1
}

COLUMNS = {
    "concept_name": [COL.CONCEPT_NAME, "concept_name", "概念名称", "name", "题材名称"],
    "increment": [COL.INCREMENT_BILLION, "净流入", "increment", "增量(亿)"],
    "avg_change": [COL.AVG_CHANGE_PCT, "平均涨幅", "avg_change", "平均涨跌%"],
    "leader": [COL.INCREMENT_LEADER, "增量先锋", "leader"],
    "amount": ["成交额", "amount", "总成交额", "总成交额(亿)", "金额"],
    "big_up_rate": ["大涨率%", "big_up_rate", "大涨率"],
    "big_down_rate": ["大跌率%", "big_down_rate", "大跌率"],
    "code": [COL.CODE, "股票代码", "code", "代码"],
    "name": [COL.NAME, "股票简称", "name", "名称"],
    "pct_chg": [COL.PCT_CHG, "涨跌幅", "pct_chg", "涨幅"],
    "tags": ["tags", COL.CONCEPT, "所属概念", "tags", "概念", "题材"],
    "merged_tags": ["合并标签"],
    "stock_increment": ["增量"],
    "stocks_count": ["家数", "stocks_count"],
    "limit_up_count": ["涨停数", "limit_up_count"],
    "limit_down_count": ["跌停数", "limit_down_count"],
    "continuous_limit_up_count": ["连板数", "continuous_limit_up_count"],
    "first_limit_up_count": ["首板数", "first_limit_up_count"],
    "blow_up_count": ["炸板数", "blow_up_count"],
    "big_up_count": ["大涨数", "big_up_count"],
    "big_down_count": ["大跌数", "big_down_count"],
    "red_rate": ["红盘率%", "红盘率", "red_rate"],
    "limit_up_rate": ["涨停率%", "limit_up_rate"],
    "limit_down_rate": ["跌停率%", "limit_down_rate"],
    "limit_up_stocks": ["涨停股票", "连板股票", "limit_up_stocks"],
    "leader_code": ["先锋代码", "leader_code"],
    "date": ["日期", "date"],
    "stage": ["阶段", "stage"],
}

COLUMN_LABELS = {
    "concept_name": "题材名称",
    "increment": "增量(亿)",
    "avg_change": "平均涨跌%",
    "amount": "总成交额(亿)",
    "leader": "增量先锋",
    "big_up_rate": "大涨率%",
    "big_down_rate": "大跌率%",
    "red_rate": "红盘率%",
    "limit_up_count": "涨停数",
    "limit_down_count": "跌停数",
    "big_up_count": "大涨数",
    "big_down_count": "大跌数",
    "continuous_limit_up_count": "连板数",
    "first_limit_up_count": "首板数",
    "blow_up_count": "炸板数",
    "stocks_count": "家数",
    "limit_up_rate": "涨停率%",
    "limit_down_rate": "跌停率%",
    "limit_up_stocks": "涨停股票",
    "leader_code": "先锋代码",
    "date": "日期",
    "stage": "阶段",
}


# =============================================================================
# 模块 2: 高亮与样式
# =============================================================================

def _check_numeric_condition(value, threshold):
    """检查数值条件"""
    try:
        return float(value) > threshold
    except:
        return False


def _check_string_contains(value, substring):
    """检查字符串包含条件"""
    try:
        return substring in str(value)
    except:
        return False


def _precompute_column_indices(df: pd.DataFrame):
    """预先计算高亮函数需要的列索引（使用标准列名）"""
    standard_cols = {
        'stocks': ['stocks_count', '家数'],
        'red': ['red_rate', '红盘率%', '红盘率'],
        'avg_chg': ['avg_change'],
        'inc': ['increment'],
        'leader': ['leader']
    }
    
    cols = {}
    for key, possible_names in standard_cols.items():
        for col in possible_names:
            if col in df.columns:
                cols[key] = col
                break
    return cols


def highlight_concepts(row, col_indices):
    """
    高亮概念题材表格中的符合条件的行
    
    强共振条件（全部满足整行红色）：
    - 家数 > 10
    - 红盘率% > 75
    - 平均涨跌% > 1.2
    - 资金增量(亿) > 1
    - 增量先锋包含'突发放量'
    
    部分满足单项淡黄色高亮
    """
    required_cols = ['stocks', 'red', 'avg_chg', 'inc']
    if not all(col in col_indices for col in required_cols):
        return [''] * len(row)
    
    conditions = {
        'stocks': _check_numeric_condition(row[col_indices['stocks']], STRONG_CONCEPT_CONDITIONS['min_stocks']),
        'red': _check_numeric_condition(row[col_indices['red']], STRONG_CONCEPT_CONDITIONS['min_red_ratio']),
        'avg_chg': _check_numeric_condition(row[col_indices['avg_chg']], STRONG_CONCEPT_CONDITIONS['min_change']),
        'inc': _check_numeric_condition(row[col_indices['inc']], STRONG_CONCEPT_CONDITIONS['min_fund']),
        'leader': _check_string_contains(row[col_indices['leader']], '突发放量') if 'leader' in col_indices else False
    }
    
    all_conditions_met = all(conditions.values())
    
    if all_conditions_met:
        return ['background-color: #FFCCCC; color: black; font-weight: bold'] * len(row)
    
    styles = [''] * len(row)
    for i, col_name in enumerate(row.index):
        for key, col in col_indices.items():
            if col_name == col and conditions[key]:
                styles[i] = 'background-color: #FFFFE0; color: black;'
                break
    
    return styles


# =============================================================================
# 模块 3: Session State 管理
# =============================================================================

def init_session_state():
    """初始化 session_state"""
    pass


# =============================================================================
# 模块 4: 工具函数
# =============================================================================

_column_cache = {}


def _get_df_id(df: pd.DataFrame) -> int:
    """获取DataFrame的唯一标识符用于缓存"""
    return id(df)


def _build_column_cache(df: pd.DataFrame):
    """为DataFrame构建完整的列名缓存"""
    df_id = _get_df_id(df)
    cache = {}
    for col_type, possible_names in COLUMNS.items():
        for col in possible_names:
            if col in df.columns:
                cache[col_type] = col
                break
    _column_cache[df_id] = cache
    return cache


def _find_column(df: pd.DataFrame, col_type: str) -> str:
    """从DataFrame中查找指定类型的列名（带缓存）"""
    df_id = _get_df_id(df)
    
    if df_id not in _column_cache:
        _build_column_cache(df)
    
    return _column_cache[df_id].get(col_type, "")


def _clear_column_cache():
    """清除列名缓存（可选，用于释放内存）"""
    global _column_cache
    _column_cache = {}


def _load_concept_data(target_date: datetime, stage: str):
    """加载指定日期和类型的题材数据"""
    res_stats, res_details = market_service.get_concept_data(target_date, data_type=stage)
    return res_stats, res_details


def _filter_stocks_by_concept(df_stocks: pd.DataFrame, concept_name: str) -> pd.DataFrame:
    """筛选包含指定题材的股票"""
    concept_col = _find_column(df_stocks, "tags")
    if not concept_col or concept_col not in df_stocks.columns:
        return pd.DataFrame()
    
    mask = df_stocks[concept_col].apply(
        lambda x: concept_name in x if isinstance(x, list) else concept_name in str(x)
    )
    return df_stocks[mask].copy()


def _format_amount_column(df: pd.DataFrame, amount_col: str) -> pd.DataFrame:
    """转换成交额为亿单位"""
    if amount_col and amount_col in df.columns:
        df[amount_col] = df[amount_col] / 1e8
    return df


def _sort_by_amount(df: pd.DataFrame, amount_col: str) -> pd.DataFrame:
    """按成交额排序"""
    if amount_col and amount_col in df.columns:
        return df.sort_values(amount_col, ascending=False)
    return df


def _build_column_config(df: pd.DataFrame, col_type: str, label: str, width: str = "medium", fmt: str = None):
    """构建列配置"""
    col = _find_column(df, col_type)
    if not col:
        return None
    
    config = st.column_config.TextColumn(label, width=width) if not fmt else st.column_config.NumberColumn(label, width=width, format=fmt)
    return (col, config)


def _parse_concepts_list(stock_concepts):
    """解析股票的题材列表"""
    if isinstance(stock_concepts, list):
        return stock_concepts
    elif isinstance(stock_concepts, str):
        return [c.strip() for c in stock_concepts.split(',') if c.strip()]
    else:
        return []


def _filter_concepts_by_stock_tags(df_concepts: pd.DataFrame, concepts_list: list) -> pd.DataFrame:
    """根据股票的题材列表筛选概念数据"""
    if not concepts_list or df_concepts.empty:
        return pd.DataFrame()
    
    name_col = _find_column(df_concepts, "concept_name")
    if not name_col:
        return pd.DataFrame()
    
    mask = df_concepts[name_col].apply(
        lambda x: any(c in str(x) or str(x) in c for c in concepts_list)
    )
    return df_concepts[mask].copy()


def _sort_concepts_by_increment(df_concepts: pd.DataFrame) -> pd.DataFrame:
    """按平均涨跌降序排序，平均涨跌相同则按增量排序"""
    if df_concepts.empty:
        return df_concepts
    
    sort_cols = []
    ascending_list = []
    
    if "avg_change" in df_concepts.columns:
        sort_cols.append("avg_change")
        ascending_list.append(False)
    if "increment" in df_concepts.columns:
        sort_cols.append("increment")
        ascending_list.append(False)
    
    if sort_cols:
        return df_concepts.sort_values(by=sort_cols, ascending=ascending_list)
    return df_concepts


def _standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """标准化DataFrame的列名为COLUMNS配置中的标准key"""
    if df.empty:
        return df.copy()
    
    col_mapping = {}
    
    for standard_key, possible_names in COLUMNS.items():
        for col in df.columns:
            if col in possible_names:
                col_mapping[col] = standard_key
                break
    
    df_standardized = df.rename(columns=col_mapping)
    return df_standardized


def _ensure_numeric_for_stocks(df: pd.DataFrame) -> pd.DataFrame:
    """确保个股数据的数值列为正确的数值类型"""
    if df.empty:
        return df
    
    # 定义需要转换为数值的列及其对应的标准列名
    numeric_cols_map = {
        'pct_chg': ['pct_chg', '涨跌幅', '涨幅', 'PCT_CHG'],
        'increment': ['increment', '净流入', '增量', '增量(亿)', 'INCREMENT_BILLION'],
        'amount': ['amount', '成交额', '金额', '总成交额', 'STD_AMOUNT']
    }
    
    for standard_name, possible_names in numeric_cols_map.items():
        # 查找实际存在的列名
        actual_col = None
        for col in df.columns:
            if col in possible_names:
                actual_col = col
                break
        
        if actual_col:
            # 转换为数值类型，无法转换的设为NaN
            df[actual_col] = pd.to_numeric(df[actual_col], errors='coerce')
    
    return df


# =============================================================================
# 模块 5: 图表渲染
# =============================================================================

def _create_mini_bar_chart(df: pd.DataFrame, x_col: str, y_col: str, title: str, 
                           color: str = '#4facfe', use_red_green: bool = False,
                           text_decimals: int = 2):
    """创建通用的迷你柱状图"""
    fig = go.Figure()
    
    if use_red_green:
        colors = ['#d62728' if x > 0 else '#2ca02c' for x in df[y_col]]
    else:
        colors = color
    
    text_values = df[y_col].round(text_decimals) if text_decimals >= 0 else df[y_col]
    
    fig.add_trace(go.Bar(
        x=df[x_col], 
        y=df[y_col],
        marker_color=colors,
        text=text_values,
        textposition='outside'
    ))
    
    fig.update_layout(
        height=200, 
        template="plotly_white", 
        margin=dict(l=10, r=10, t=30, b=0),
        xaxis=dict(showticklabels=False),
        title=title, 
        title_x=0.5
    )
    return fig


def _render_concept_chart(df_concepts: pd.DataFrame):
    """渲染题材多维度图表"""
    if df_concepts.empty:
        return
    
    if "concept_name" not in df_concepts.columns:
        return
    
    df_top15 = df_concepts.head(15).copy()
    cols = st.columns(5)
    
    chart_configs = [
        ("increment", "💰 增量资金(亿)", True, '#4facfe', 2),
        ("avg_change", "📈 涨幅%", True, '#4facfe', 2),
        ("amount", "💵 成交额(亿)", False, '#4facfe', 2),
    ]
    
    for i, (y_col, title, use_red_green, color, decimals) in enumerate(chart_configs):
        with cols[i]:
            if y_col in df_top15.columns:
                fig = _create_mini_bar_chart(df_top15, "concept_name", y_col, title,
                                             color=color, use_red_green=use_red_green, 
                                             text_decimals=decimals)
                st.plotly_chart(fig, width='stretch')
    
    with cols[3]:
        if "red_rate" in df_top15.columns:
            fig = _create_mini_bar_chart(df_top15, "concept_name", "red_rate", "🔥 红盘率%", 
                                         color='#52c41a', use_red_green=False, text_decimals=1)
            st.plotly_chart(fig, width='stretch')
    
    with cols[4]:
        zt_col = "limit_up_count" if "limit_up_count" in df_top15.columns else None
        dt_col = "limit_down_count" if "limit_down_count" in df_top15.columns else None
        big_up_col = "big_up_rate" if "big_up_rate" in df_top15.columns else None
        big_down_col = "big_down_rate" if "big_down_rate" in df_top15.columns else None
        
        if zt_col or dt_col:
            fig5 = make_subplots(specs=[[{"secondary_y": True}]])
            if zt_col:
                fig5.add_trace(go.Bar(
                    x=df_top15["concept_name"], 
                    y=df_top15[zt_col],
                    name="涨停",
                    marker_color='#d62728',
                    text=df_top15[zt_col],
                    textposition='outside'
                ), secondary_y=False)
            if dt_col:
                fig5.add_trace(go.Bar(
                    x=df_top15["concept_name"], 
                    y=df_top15[dt_col],
                    name="跌停",
                    marker_color='#2ca02c',
                    text=df_top15[dt_col],
                    textposition='outside'
                ), secondary_y=False)
            if big_up_col and big_up_col in df_top15.columns:
                fig5.add_trace(go.Scatter(
                    x=df_top15["concept_name"],
                    y=df_top15[big_up_col],
                    name="大涨率",
                    line=dict(color='#ff4d4f', width=2),
                    mode='lines+markers'
                ), secondary_y=True)
            if big_down_col and big_down_col in df_top15.columns:
                fig5.add_trace(go.Scatter(
                    x=df_top15["concept_name"],
                    y=df_top15[big_down_col],
                    name="大跌率",
                    line=dict(color='#2ecc71', width=2),
                    mode='lines+markers'
                ), secondary_y=True)
            fig5.update_layout(
                height=200, 
                template="plotly_white", 
                margin=dict(l=10, r=10, t=30, b=0),
                xaxis=dict(showticklabels=False),
                barmode='group',
                showlegend=False,
                title="🚀 涨跌停", title_x=0.5
            )
            st.plotly_chart(fig5, width='stretch')


def _render_concept_summary(df_concepts: pd.DataFrame):
    """渲染题材汇总信息"""
    if "concept_name" in df_concepts.columns and "increment" in df_concepts.columns and not df_concepts.empty:
        top = df_concepts.iloc[0]
        st.caption(f"**最强题材:** {top['concept_name']} | **净流入:** {top['increment']:.2f}亿")


# =============================================================================
# 模块 6: 表格渲染
# =============================================================================

def _render_concept_table(df_concepts: pd.DataFrame, stage: str, target_date: datetime):
    """渲染题材表格（选中行弹窗）"""
    if df_concepts.empty:
        st.warning("暂无数据")
        return
    
    # 先找到题材名称列，用于下钻功能
    name_col = "concept_name" if "concept_name" in df_concepts.columns else None
    
    column_labels = COLUMN_LABELS
    
    col_config = {}
    
    for col in df_concepts.columns:
        if col == 'index':
            continue
        
        # 获取显示名
        display_name = column_labels.get(col, col)
        
        if col == 'concept_name':
            col_config[col] = st.column_config.TextColumn(display_name, width="medium")
        elif col == 'leader' or col == 'limit_up_stocks' or col == 'continuous_limit_up_stocks':
            col_config[col] = st.column_config.TextColumn(display_name, width="medium")
        elif col == 'leader_code':
            col_config[col] = st.column_config.TextColumn(display_name, width="small")
        elif '%' in display_name or 'rate' in col:
            col_config[col] = st.column_config.NumberColumn(display_name, format="%.2f", width="small")
        elif '亿' in display_name or 'increment' in col or 'amount' in col:
            col_config[col] = st.column_config.NumberColumn(display_name, format="%.2f", width="small")
        elif 'count' in col or col in ['stocks_count']:
            col_config[col] = st.column_config.NumberColumn(display_name, format="%d", width="small")
        else:
            col_config[col] = st.column_config.TextColumn(display_name, width="small")
    
    preferred_cols = []
    core_order = ['concept_name', 'stocks_count', 'increment', 'avg_change', 'red_rate', 
                 'limit_up_count', 'limit_up_rate', 'big_up_rate', 'big_down_rate', 
                 'limit_down_rate', 'limit_down_count', 'amount', 'leader']
    
    for col in core_order:
        if col in df_concepts.columns:
            preferred_cols.append(col)
    
    # 添加涨停/连板股票列
    if 'limit_up_stocks' in df_concepts.columns:
        preferred_cols.append('limit_up_stocks')
    
    # 添加连板、首板、炸板、大涨数、大跌数列
    for col in ['continuous_limit_up_count', 'first_limit_up_count', 'blow_up_count', 'big_up_count', 'big_down_count']:
        if col in df_concepts.columns:
            preferred_cols.append(col)
    
    display_cols = preferred_cols.copy()
    for col in df_concepts.columns:
        if col != 'index' and col not in display_cols:
            display_cols.append(col)
    
    df_display = df_concepts[display_cols].copy()
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
    
    st.markdown("##### 📋 题材列表（勾选查看明细）")
    
    selection = st.dataframe(
        styler,
        column_config=col_config,
        width='stretch',
        height=400,
        on_select="rerun",
        selection_mode="single-row",
        hide_index=True,
        key=f"concept_table_{stage}"
    )
    
    if selection.selection["rows"]:
        selected_idx = selection.selection["rows"][0]
        concept_name = df_concepts.iloc[selected_idx].get(name_col, '')
        if concept_name:
            _show_stocks_popup(target_date, concept_name, stage)
    
    _render_concept_summary(df_concepts)
    _render_concept_chart(df_concepts)


def _render_stocks_table(df_stocks: pd.DataFrame, concept_name: str, stage: str, target_date: datetime):
    """渲染个股表格（选中行显示题材表现）"""
    df_stocks = df_stocks.copy()
    
    code_col = "code" if "code" in df_stocks.columns else None
    name_col = "name" if "name" in df_stocks.columns else None
    pct_col = "pct_chg" if "pct_chg" in df_stocks.columns else None
    amount_col = "amount" if "amount" in df_stocks.columns else None
    tags_col = "tags" if "tags" in df_stocks.columns else None
    merged_tag_col = "merged_tags" if "merged_tags" in df_stocks.columns else None
    
    inc_col = "increment" if "increment" in df_stocks.columns else None
    
    # 转换成交额单位（元 -> 亿）
    df_stocks = _format_amount_column(df_stocks, amount_col)
    
    col_config = {}
    display_cols = []
    
    if code_col:
        display_cols.append(code_col)
        col_config[code_col] = st.column_config.TextColumn("代码", width="small")
    if name_col:
        display_cols.append(name_col)
        col_config[name_col] = st.column_config.TextColumn("名称", width="medium")
    if pct_col:
        display_cols.append(pct_col)
        col_config[pct_col] = st.column_config.NumberColumn("涨幅", format="%.2f%%", width="small")
    if inc_col:
        display_cols.append(inc_col)
        col_config[inc_col] = st.column_config.NumberColumn("增量(亿)", format="%.2f", width="small")
    if amount_col:
        display_cols.append(amount_col)
        col_config[amount_col] = st.column_config.NumberColumn("成交额(亿)", format="%.2f", width="small")
    if merged_tag_col:
        display_cols.append(merged_tag_col)
        col_config[merged_tag_col] = st.column_config.TextColumn("合并标签", width="large")
    
    for col in df_stocks.columns:
        if col not in display_cols and col != tags_col:
            display_cols.append(col)
            col_config[col] = st.column_config.TextColumn(col, width="small")
    
    stock_selection = st.dataframe(
        df_stocks[display_cols],
        column_config=col_config,
        height=400,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"stocks_popup_{concept_name}"
    )
    
    if stock_selection.selection["rows"]:
        stock_idx = stock_selection.selection["rows"][0]
        stock_row = df_stocks.iloc[stock_idx]
        stock_code = stock_row.get(code_col, '')
        stock_name = stock_row.get(name_col, '')
        stock_concepts = stock_row.get(tags_col, [])
        
        _render_stock_concepts(target_date, stock_code, stock_name, stage, stock_concepts)


def _render_stock_concepts(target_date: datetime, stock_code: str, stock_name: str, stage: str, stock_concepts):
    """在弹窗内显示股票所属题材"""
    st.markdown(f"### 🎯 {stock_name} ({stock_code}) 所属题材表现")
    
    concepts_list = _parse_concepts_list(stock_concepts)
    
    if not concepts_list:
        st.info("暂无题材数据")
        return
    
    res_stats, _ = _load_concept_data(target_date, stage)
    if res_stats.status != DataStatus.OK:
        st.warning("无法加载数据")
        return
    
    df_all = res_stats.data
    df_all = _standardize_column_names(df_all)
    df_result = _filter_concepts_by_stock_tags(df_all, concepts_list)
    
    if df_result.empty:
        st.info("暂无题材数据")
        return
    
    df_result = _sort_concepts_by_increment(df_result)
    
    if "concept_name" not in df_result.columns:
        st.warning("未找到题材名称列")
        return
    
    name_col = "concept_name"
    inc_col = "increment" if "increment" in df_result.columns else None
    avg_col = "avg_change" if "avg_change" in df_result.columns else None
    
    display_cols = [name_col]
    if inc_col:
        display_cols.append(inc_col)
    if avg_col:
        display_cols.append(avg_col)
    
    col_config = {}
    if inc_col:
        col_config[inc_col] = st.column_config.NumberColumn("净流入(亿)", format="%.2f")
    if avg_col:
        col_config[avg_col] = st.column_config.NumberColumn("平均涨幅", format="%.2f%%")
    
    st.dataframe(
        df_result[display_cols],
        column_config=col_config,
        height=250,
        hide_index=True
    )


# =============================================================================
# 模块 7: 弹窗/下钻
# =============================================================================

def _show_stocks_popup(target_date: datetime, concept_name: str, stage: str):
    """显示题材对应的个股弹窗"""
    @st.dialog(f"📊 {concept_name}", width="large")
    def popup():
        st.markdown(f"### 📊 {concept_name} ({stage}) 个股明细")
        
        _, res = _load_concept_data(target_date, stage)
        if res.status == DataStatus.OK:
            df_stocks = res.data
            # 标准化列名并转换数值类型
            df_stocks = _standardize_column_names(df_stocks)
            df_stocks = _ensure_numeric_for_stocks(df_stocks)
            sub_df = _filter_stocks_by_concept(df_stocks, concept_name)
            
            if sub_df.empty:
                st.info("暂无个股数据")
            else:
                _render_stocks_table(sub_df, concept_name, stage, target_date)
        else:
            st.warning("无法加载数据")
    
    popup()


def _show_stock_concepts_popup(target_date: datetime, stock_code: str, stock_name: str, stage: str, stock_concepts):
    """显示股票所属题材的弹窗"""
    @st.dialog(f"🎯 {stock_name}", width="large")
    def popup():
        _render_stock_concepts(target_date, stock_code, stock_name, stage, stock_concepts)
    
    popup()


# =============================================================================
# 模块 8: 搜索功能
# =============================================================================

def render_search_area(selected_date_obj: datetime, data_type: str, df_concepts_all: pd.DataFrame):
    """渲染搜索区域"""
    with st.expander("🔍 全局搜索 (概念/股票)", expanded=False):
        c1, c2 = st.columns([1, 4])
        with c1:
            st.selectbox(
                "类型", ["全部", "概念", "股票"], 
                key=f"search_type_{data_type}",
                label_visibility="collapsed"
            )
        with c2:
            query = st.text_input(
                "关键词", 
                placeholder="输入代码、简称或概念名称...",
                key=f"search_query_{data_type}",
                label_visibility="collapsed"
            )

        if query:
            search_type = st.session_state.get(f"search_type_{data_type}", "全部")
            _execute_search(query, search_type, selected_date_obj, data_type, df_concepts_all)


def _execute_search(query: str, search_type: str, date_obj: datetime, data_type: str, df_concepts: pd.DataFrame):
    """执行搜索逻辑"""
    query = query.strip().lower()
    if not query:
        return

    results_found = False
    query_hash = abs(hash(query)) % 10000

    if search_type in ["全部", "概念"]:
        if not df_concepts.empty:
            if "concept_name" in df_concepts.columns:
                name_col = "concept_name"
                matches = df_concepts[
                    df_concepts[name_col].str.lower().str.contains(query, na=False)
                ]
                if not matches.empty:
                    results_found = True
                    st.markdown(f"**📊 概念匹配 ({len(matches)})**")
                    
                    cols = st.columns(4)
                    for idx, row in enumerate(matches.head(8).to_dict('records')):
                        with cols[idx % 4]:
                            c_name = row.get(name_col, '未知')
                            avg_chg = row.get("avg_change", 0)
                            
                            label = f"{c_name}\n(涨:{avg_chg:.1f}%)" if avg_chg else f"{c_name}"
                            button_key = f"s_c_{data_type}_{query_hash}_{idx}_{c_name}"
                            if st.button(label, key=button_key):
                                _show_stocks_popup(date_obj, c_name, data_type)

    if search_type in ["全部", "股票"]:
        _, res_details = _load_concept_data(date_obj, data_type)
        if res_details.status == DataStatus.OK and not res_details.data.empty:
            df_stocks = res_details.data
            df_stocks = _standardize_column_names(df_stocks)
            _build_column_cache(df_stocks)
            
            code_col = "code" if "code" in df_stocks.columns else None
            name_col = "name" if "name" in df_stocks.columns else None
            
            if code_col or name_col:
                mask = pd.Series([False] * len(df_stocks))
                if code_col:
                    mask |= df_stocks[code_col].str.lower().str.contains(query, na=False)
                if name_col:
                    mask |= df_stocks[name_col].str.lower().str.contains(query, na=False)
                
                matches = df_stocks[mask].head(8)
                if not matches.empty:
                    results_found = True
                    st.markdown(f"**📈 股票匹配 ({len(matches)})**")
                    
                    cols = st.columns(4)
                    for idx, row in enumerate(matches.to_dict('records')):
                        with cols[idx % 4]:
                            s_code = row.get(code_col, '') if code_col else ''
                            s_name = row.get(name_col, '') if name_col else ''
                            label = f"{s_name}\n{s_code}" if s_name else s_code
                            button_key = f"s_s_{data_type}_{query_hash}_{idx}_{s_code}"
                            if st.button(label, key=button_key):
                                stock_concepts = row.get("tags", [])
                                stock_concepts = _parse_concepts_list(stock_concepts)
                                _show_stock_concepts_popup(date_obj, s_code, s_name, data_type, stock_concepts)

    if not results_found:
        st.warning("未找到匹配结果")


# =============================================================================
# 模块 9: 主入口
# =============================================================================

def render_concept_dashboard(target_date: datetime):
    """题材共振页面 - 表格选中弹窗下钻"""
    init_session_state()
    _clear_column_cache()
    
    date_str = target_date.strftime('%Y-%m-%d')
    st.caption(f"📅 日期: {date_str}")
    
    res_stats_auc, res_details_auc = _load_concept_data(target_date, "竞价")
    res_stats_close, res_details_close = _load_concept_data(target_date, "收盘")
    
    if res_stats_auc.status == DataStatus.OK:
        res_stats_auc.data = _standardize_column_names(res_stats_auc.data)
        res_stats_auc.data = _sort_concepts_by_increment(res_stats_auc.data)
    if res_details_auc.status == DataStatus.OK:
        res_details_auc.data = _standardize_column_names(res_details_auc.data)
    if res_stats_close.status == DataStatus.OK:
        res_stats_close.data = _standardize_column_names(res_stats_close.data)
        res_stats_close.data = _sort_concepts_by_increment(res_stats_close.data)
    if res_details_close.status == DataStatus.OK:
        res_details_close.data = _standardize_column_names(res_details_close.data)
    
    if res_stats_auc.status != DataStatus.OK and res_stats_close.status != DataStatus.OK:
        st.warning("暂无题材数据")
        return
    
    tab1, tab2 = st.tabs(["🚀 竞价", "🏁 收盘"])
    
    with tab1:
        if res_stats_auc.status == DataStatus.OK:
            render_search_area(target_date, "竞价", res_stats_auc.data)
            st.divider()
            _render_concept_table(res_stats_auc.data, "竞价", target_date)
        else:
            st.info("⏳ 竞价数据尚未生成")
    
    with tab2:
        if res_stats_close.status == DataStatus.OK:
            render_search_area(target_date, "收盘", res_stats_close.data)
            st.divider()
            _render_concept_table(res_stats_close.data, "收盘", target_date)
        else:
            st.info("⏳ 收盘数据尚未生成")


if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="题材共振")
    from datetime import date
    render_concept_dashboard(date.today())

