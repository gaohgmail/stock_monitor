
# -*- coding: utf-8 -*-
# aaaa_NEW.py

# =========================================================
# 1. 系统与基础库
# =========================================================
import os
import sys
import datetime
import requests
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

# =========================================================
# 2. Streamlit 与 绘图库
# =========================================================
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 必须作为第一个 Streamlit 命令 ---
st.set_page_config(page_title="量化复盘系统", layout="wide")

# =========================================================
# 3. 项目路径修复 (确保能够正确识别 modules 文件夹)
# =========================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# =========================================================
# 4. 导入自定义模块 (从 modules 文件夹)
# =========================================================
# 配置与通用工具
from modules.config import *
from modules.utils import (
    Logger, safe_read_csv, standardize_code, 
    clean_dataframe, check_password, trigger_github_action
)

# 数据加载与核心分析逻辑
from modules.data_loader import get_trade_dates, read_market_data
from modules.analyzer_market import (
    get_sentiment_trend_report, 
)

# UI 渲染页面 (分模块)
from modules.ui_sentiment import render_sentiment_dashboard
from modules.ui_top_stocks import render_top_turnover_page

# =========================================================
# 5. 后续逻辑开始 (if check_password(): ...)
# =========================================================

# 1. 页面配置
st.set_page_config(page_title="量化复盘系统", layout="wide")

# 2. 身份校验
if check_password():
    # 3. 全局数据加载 (使用缓存)
    LOOKBACK_DAYS = 30
    trade_dates = get_trade_dates(LOOKBACK_DAYS)
    report_df = get_sentiment_trend_report(trade_dates)

    # 4. 侧边栏控制
# aaaa_NEW.py 核心修改部分

# 4. 侧边栏控制
with st.sidebar:
    st.title("🎯 功能导航")
    
    # --- A. 页面标签选择放在顶部 ---
    page_selection = st.radio(
        "请选择功能模块：",
        ["📈 市场情绪", "🏆 成交榜单", "🔍 个股诊断"],
        index=0,
        key="navigation"
    )

    st.markdown("---") # 分割线
    
    # --- B. 原有的控制中心内容移到下方 ---
    with st.expander("⚙️ 数据控制中心", expanded=True):
        st.write("数据配置")
        # 日期选择
        all_dates = pd.to_datetime(report_df['日期']).dt.date
        target_date = st.date_input("目标日期", value=all_dates.max())
        
        # 功能触发按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 抓取数据", use_container_width=True):
                trigger_github_action()
        with col2:
            if st.button("🔄 同步数据", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    # 侧边栏底部信息
    st.sidebar.markdown(f"---")
    st.sidebar.caption(f"⏰ 刷新时间: {datetime.datetime.now().strftime('%H:%M:%S')}")

# 5. 核心：根据侧边栏的选择渲染页面
# 不再使用 tab1, tab2, tab3 = st.tabs(...)

target_date_str = target_date.strftime('%Y-%m-%d')
target_row = report_df[report_df['日期'] == target_date_str]

if page_selection == "📈 市场情绪":
    if not target_row.empty:
        render_sentiment_dashboard(target_row)
    else:
        st.error(f"未找到 {target_date_str} 的分析数据")

elif page_selection == "🏆 成交榜单":
    render_top_turnover_page(target_date)

elif page_selection == "🔍 个股诊断":
    st.info("个股诊断模块开发中...")
