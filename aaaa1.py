
# -*- coding: utf-8 -*-
# aaaa1.py
import sys
import os
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import requests
from concurrent.futures import ThreadPoolExecutor
# --- 0. Streamlit 页面配置 (必须作为第一个 st 命令) ---
st.set_page_config(page_title="市场情绪双时段监控", layout="wide")

# --- 1. 环境与路径设置 ---
#PROJECT_ROOT = Path(__file__).parent.parent
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
#PROJECT_ROOT = "D:/数据处理/测试修改"
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# 导入自定义模块
from modules.config import *
from modules.utils import Logger, safe_read_csv, standardize_code, clean_dataframe
from modules.data_loader import get_trade_dates, read_market_data
from modules.analyzer import build_structure_tags, analyze_auction_flow
import streamlit as st
# ... 之前的 import ...
from modules.ui_sentiment import render_sentiment_dashboard  # 移过去的函数
from modules.ui_top_stocks import render_top_turnover_page   # 新函数

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
