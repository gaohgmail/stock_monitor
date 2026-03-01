"""
百分位计算器 - 逻辑反转标准化版
1. 统一逻辑：对'跌停'、'极弱'执行反转计算(100-rank)，使所有指标数值含义保持一致（高分好，低分冰点）。
2. 自动化引擎：一键适配'竞价_'与'收盘_'，支持动态列检测。
3. 性能优化：全量向量化滚动计算，毫秒级响应。
4. 视觉对齐：数值低（冰点/反转位）时高亮显示，符合交易直觉。
"""
import sys
from tools.config import PROJECT_ROOT

# 使用config中的项目根路径
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
import numpy as np

# ==================== 1. 配置中心 ====================

# 基础映射表：键(原始名) -> 值(显示名后缀)
INDICATOR_CONFIG = {
    '总额': '成交额百分位',
    '全场涨跌比': '涨跌比_pct',
    '核心溢价': '核心溢价_pct',
    '核心赚钱': '核心赚钱_pct',
    '核心承接': '核心承接_pct',
    '妖股溢价': '妖股溢价_pct',
    '妖股赚钱': '妖股赚钱_pct',
    '妖股承接': '妖股承接_pct',
    '前15占比': '前15占比_pct',
    '创业额': '创业额百分位',
    '涨停': '涨停数百分位',
    '强力': '强力数百分位',
    # --- 以下为反转指标 ---
    '跌停': '跌停数百分位', 
    '极弱': '极弱数百分位',
}

# 需要执行 100 - x 反转逻辑的指标后缀
REVERSION_LIST = ['跌停数百分位', '极弱数百分位']

# ==================== 2. 计算引擎 ====================

def calculate_market_dna(df, prefix='收盘_', window=60):
    """
    核心计算引擎：负责百分位计算、逻辑反转及无效数据遮罩
    """
    df = df.copy()
    original_cols = df.columns.tolist()
    
    for base_name, suffix in INDICATOR_CONFIG.items():
        src_col = f"{prefix}{base_name}"
        target_col = f"{prefix}{suffix}"
        
        if src_col in df.columns:
            # A. 计算基础排名百分位 (0-100)
            rank_pct = (
                df[src_col]
                .rolling(window=window, min_periods=1)
                .rank(pct=True)
                .mul(100)
            )
            
            # B. 逻辑反转：负面指标执行 100 - rank，数值越小代表负面情绪越极端
            if suffix in REVERSION_LIST:
                df[target_col] = (100 - rank_pct).round(1)
            else:
                df[target_col] = rank_pct.round(1)

    # C. 掩码保护：若当前阶段成交额为0，代表该行特征尚未产生，重置为NaN以防误导
    vol_col = f"{prefix}总额"
    if vol_col in df.columns:
        new_cols = [c for c in df.columns if c not in original_cols]
        invalid_mask = (df[vol_col] == 0) | (df[vol_col].isna())
        if invalid_mask.any():
            df.loc[invalid_mask, new_cols] = np.nan
            
    return df

# ==================== 3. 视觉渲染 ====================

def style_sentiment_cells(val):
    """
    视觉优化版：
    - 数值极高 (>= 80): 强势/安全区 -> 淡红色 (Light Red)
    - 数值极低 (<= 20): 冰点/反转位 -> 淡绿色 (Light Green)
    """
    if pd.isna(val): return ''
    
    # 高分：强势（淡红）
    if val >= 80:
        return 'background-color: #FFC1C1; color: #8B0000; font-weight: bold' 
    
    # 低分：冰点/弱势（淡绿）
    elif val <= 20:
        return 'background-color: #C1FFC1; color: #006400; font-weight: bold'
        
    return 'color: #333333' # 中间数值保持深灰色，增加对比度

def render_sentiment_table(df, stage_name="收盘"):
    """
    表格渲染包装器
    """
    prefix = f"{stage_name}_"
    st.subheader(f"📊 {stage_name}阶段 - 百分位分布")
    
    # 自动筛选展示列
    display_cols = ['日期'] + [c for c in df.columns if c.startswith(prefix) and ('pct' in c or '百分位' in c)]
    
    if len(display_cols) <= 1:
        st.info(f"暂无{stage_name}阶段有效特征列")
        return

    # 预处理显示数据
    view_df = df[display_cols].copy()
    view_df['日期'] = pd.to_datetime(view_df['日期']).dt.strftime('%Y-%m-%d')
    view_df = view_df.sort_values('日期', ascending=False)

    # 应用条件格式：所有百分位列均适用同一逻辑（低值反转，高值走强）
    data_cols = [c for c in view_df.columns if c != '日期']
    
    st.dataframe(
        view_df.style.applymap(style_sentiment_cells, subset=data_cols).format(precision=1),
        hide_index=True, 
        use_container_width=True
    )

# ==================== 4. Streamlit 主程序 ====================

def main():
    st.set_page_config(page_title="DNA百分位看板", layout="wide")
    st.title("📊 市场情绪DNA百分位看板")
    st.info("💡 逻辑说明：跌停/极弱已执行反转计算。全表数值越小(<=20)代表情绪越接近冰点，博弈反转；数值越高越强。")
    
    with st.sidebar:
        st.header("⚙️ 设置")
        window = st.slider("百分位滚动窗口", 5, 120, 60, 5)
        days = st.slider("数据回溯天数", 60, 300, 150, 10)
        mode = st.selectbox("显示模式", ["双阶段对比", "仅竞价", "仅收盘"])

    try:
        # 数据加载
        from tools.data_loader import get_trade_dates
        from core.service_layer import market_service
        
        with st.spinner("同步数据中..."):
            all_dates = get_trade_dates(count=days)
            df = market_service.get_market_sentiment(list(all_dates))
            
            if df.empty:
                st.error("数据加载失败，请检查服务层连接")
                return

            df['日期'] = pd.to_datetime(df['日期'])
            df = df.sort_values('日期').reset_index(drop=True)

        # 执行双阶段计算
        df = calculate_market_dna(df, prefix='竞价_', window=window)
        df = calculate_market_dna(df, prefix='收盘_', window=window)

        # 动态渲染
        if mode in ["双阶段对比", "仅竞价"]:
            render_sentiment_table(df, "竞价")
        
        if mode in ["双阶段对比", "仅收盘"]:
            render_sentiment_table(df, "收盘")

    except Exception as e:
        st.error(f"系统运行异常: {e}")

# 在 percentile_calculator.py 文件的最末尾
if __name__ == "__main__":
    # 只有直接运行这个文件时，才会启动 Streamlit 界面
    main()
