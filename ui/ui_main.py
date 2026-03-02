# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

# 1. 路径与配置
st.set_page_config(page_title="Quant V3 复盘系统", layout="wide", initial_sidebar_state="expanded")

# 确保能找到项目根目录下的模块
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 2. 导入核心模块
from tools.data_loader import get_trade_dates
from tools.date_utils import ensure_datetime
from core.service_layer import market_service
from ui.ui_sentiment_v2 import render_sentiment_dashboard
from ui.ui_top15gupiao_v2 import render_top15_dashboard

def main():
    # --- 侧边栏交互区 ---
    with st.sidebar:
        st.title("📊 Quant V3")
        
        # 加载交易日历
        all_dates = get_trade_dates(count=60)
        if not all_dates:
            st.error("无法加载交易日历，请检查数据源")
            return

        # 初始化 Session State
        if 'selected_date' not in st.session_state:
            st.session_state.selected_date = all_dates[-1]
        if 'current_page' not in st.session_state:
            st.session_state.current_page = "市场情绪"

        # 1. 页面导航按钮
        st.subheader("导航")
        pages = {
            "📈 市场情绪": "市场情绪",
            "🏆 个股趋势": "个股趋势"
        }
        
        for label, p_name in pages.items():
            if st.button(label, use_container_width=True, 
                         type="primary" if st.session_state.current_page == p_name else "secondary"):
                st.session_state.current_page = p_name
                st.rerun()

        st.markdown("---")
        
        # 2. 日期选择器
        st.subheader("选择日期")
        current_idx = all_dates.index(st.session_state.selected_date) if st.session_state.selected_date in all_dates else len(all_dates)-1
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("◀ 前一天", use_container_width=True, disabled=current_idx <= 0):
                st.session_state.selected_date = all_dates[current_idx - 1]
                st.rerun()
        with col2:
            if st.button("后一天 ▶", use_container_width=True, disabled=current_idx >= len(all_dates)-1):
                st.session_state.selected_date = all_dates[current_idx + 1]
                st.rerun()
        
        selected_date = st.selectbox("跳转到日期", reversed(all_dates), index=len(all_dates)-1-current_idx)
        if selected_date != st.session_state.selected_date:
            st.session_state.selected_date = selected_date
            st.rerun()

        st.markdown("---")
        
        # 3. 刷新控制
        if st.button("🧹 清除缓存并刷新", use_container_width=True):
            market_service.clear_memory_cache()
            st.cache_data.clear()
            st.rerun()

    # --- 主界面内容区 ---
    target_dt = st.session_state.selected_date
    page = st.session_state.current_page
    
    st.header(f"{page} - {target_dt.strftime('%Y-%m-%d')}")

    if page == "市场情绪":
        # 获取最近40个交易日的数据用于绘图
        valid_dates = [d for d in all_dates if d <= target_dt][-40:]
        df_trend = market_service.get_market_sentiment(list(valid_dates))
        if not df_trend.empty:
            render_sentiment_dashboard(df_trend)
        else:
            st.warning("该日期下暂无情绪数据")

    elif page == "个股趋势":
        # 获取当日Top15数据
        df_top15 = market_service.get_top15_data(target_dt)
        if not df_top15.empty:
            render_top15_dashboard(
                df_top15[df_top15['类型']=='竞价'], 
                df_top15[df_top15['类型']=='收盘'], 
                target_dt
            )
        else:
            st.warning(f"未找到 {target_dt.strftime('%Y-%m-%d')} 的趋势分析数据")

if __name__ == "__main__":
    main()
