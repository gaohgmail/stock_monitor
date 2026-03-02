# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

# 1. 路径与配置
st.set_page_config(page_title="Quant V3 复盘系统", layout="wide")
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 2. 导入模块
from tools.data_loader import get_trade_dates
from tools.date_utils import ensure_datetime
from core.service_layer import market_service, DataStatus
from ui.ui_sentiment_v2 import render_sentiment_dashboard
from ui.ui_top15gupiao_v2 import render_top15_dashboard

def main():
    with st.sidebar:
        st.title("📊 Quant V3")
        all_dates = get_trade_dates(count=60)
        if not all_dates:
            st.error("无法加载交易日历")
            return

        if 'selected_date' not in st.session_state:
            st.session_state.selected_date = all_dates[-1]

        # 页面导航
        if 'current_page' not in st.session_state:
            st.session_state.current_page = "市场情绪"
        
        pages = {"📈 市场情绪": "市场情绪", "🏆 个股趋势": "个股趋势"}
        for label, p_name in pages.items():
            if st.button(label, use_container_width=True, 
                         type="primary" if st.session_state.current_page == p_name else "secondary"):
                st.session_state.current_page = p_name
                st.rerun()

        if st.button("🧹 清除缓存", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # 主界面逻辑
    target_dt = st.session_state.selected_date
    page = st.session_state.current_page

    if page == "市场情绪":
        valid_dates = [d for d in all_dates if d <= target_dt][-40:]
        df_trend = market_service.get_market_sentiment(list(valid_dates))
        render_sentiment_dashboard(df_trend)
    elif page == "个股趋势":
        df_top15 = market_service.get_top15_data(target_dt)
        if not df_top15.empty:
            render_top15_dashboard(df_top15[df_top15['类型']=='竞价'], 
                                 df_top15[df_top15['类型']=='收盘'], target_dt)

if __name__ == "__main__":
    main()
