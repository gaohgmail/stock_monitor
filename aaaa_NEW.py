
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
    with st.sidebar:
        st.title("🎛️ 控制中心")
        # 日期选择
        all_dates = pd.to_datetime(report_df['日期']).dt.date
        target_date = st.date_input("目标日期", value=all_dates.max())
        
        # 功能触发
        if st.button("🚀 触发 GitHub 抓取"):
            trigger_github_action()
        if st.button("🔄 同步最新数据"):
            st.cache_data.clear()
            st.rerun()

    # 5. 核心：标签页导航
    tab1, tab2, tab3 = st.tabs(["📈 市场情绪", "🏆 成交榜单", "🔍 个股诊断"])

    with tab1:
        # 这里逻辑和原 aaaa.py 一致，只是封装进了函数
        target_date_str = target_date.strftime('%Y-%m-%d')
        selected_indices = report_df[report_df['日期'] == target_date_str].index.tolist()
        if selected_indices:
            display_df = report_df.loc[:selected_indices[0]]
            render_sentiment_dashboard(display_df)
        else:
            st.error("未找到该日数据")

    with tab2:
        # 调用新页面逻辑
        render_top_turnover_page(target_date)

    with tab3:
        st.write("敬请期待：更多统计维度...")
