# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime

# ==================== 1. 页面配置 ====================
st.set_page_config(page_title="Quant V3 复盘系统", layout="wide")

# ==================== 2. 提前导入所有 UI 模块 ====================
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.data_loader import get_trade_dates
from tools.date_utils import ensure_datetime
from core.service_layer import market_service, DataStatus
from ui.ui_sentiment_v2 import render_sentiment_dashboard
from ui.ui_sentiment_analysis_deep import render_sentiment_analysis_deep
from ui.ui_top15gupiao_v2 import render_top15_dashboard
from ui.ui_zhangting import analyze_zhangting_stats, render_zhangting_dashboard, render_concept_analysis_tables
from ui.ui_concepts import render_concept_dashboard
from ui.ui_concept_analysis_deep import render_concept_analysis_deep


# ==================== 3. 核心加载逻辑 ====================
def get_sentiment_data(dates_tuple):
    """获取市场情绪数据（直接调用服务层）"""
    return market_service.get_market_sentiment(list(dates_tuple))

def get_top15_data(target_date, trend_days=30):
    """获取 Top15 数据（直接调用服务层）"""
    return market_service.get_top15_data(target_date, trend_days=trend_days)

# ==================== 4. 主程序 ====================
def main():
    
    # --- 侧边栏：全局控制 ---
    with st.sidebar:
        st.title("📊 Quant V3")
        
        # 获取日历数据
        all_dates = get_trade_dates(count=60)
        if not all_dates:
            st.error("无法加载交易日历")
            return

        # 初始化 Session State
        if 'selected_date' not in st.session_state:
            st.session_state.selected_date = all_dates[-1] # 默认最新

        # --- 侧边栏：日期导航（对齐 + 联动修复版） ---
        st.markdown("📅 **日期导航**")
        
        # 确保 session_state 存在
        if 'selected_date' not in st.session_state:
            st.session_state.selected_date = all_dates[-1]

        current_idx = all_dates.index(st.session_state.selected_date)
        
        # 1. 使用 vertical_alignment="center" 解决高度不一问题
        # 2. 比例 [1, 3, 1] 让日期框居中
        col1, col2, col3 = st.columns([1, 3, 1], vertical_alignment="center")
        
        with col1:
            if st.button("◀", key="prev_day", disabled=current_idx <= 0):
                if current_idx > 0:  # 双重检查防止越界
                    st.session_state.selected_date = all_dates[current_idx - 1]
                    st.rerun()  # 强制刷新以更新日期框的 value
        
        with col2:
            # 联动关键点：value 绑定 session_state.selected_date
            # 不要给这个 date_input 设置 key，或者 key 不要和 session_state 变量同名
            selected_date_raw = st.date_input(
                "选择日期",
                value=st.session_state.selected_date,
                min_value=all_dates[0],
                max_value=all_dates[-1],
                label_visibility="collapsed"
            )
            # 实时同步：如果手动改了日期框，立即更新 session_state
            if ensure_datetime(selected_date_raw) != st.session_state.selected_date:
                st.session_state.selected_date = ensure_datetime(selected_date_raw)
                st.rerun()
        
        with col3:
            if st.button("▶", key="next_day", disabled=current_idx >= len(all_dates)-1):
                if current_idx < len(all_dates) - 1:  # 双重检查防止越界
                    st.session_state.selected_date = all_dates[current_idx + 1]
                    st.rerun()

        st.markdown("---")
        
        # 3. 页面路由导航
        if 'current_page' not in st.session_state:
            st.session_state.current_page = "市场情绪"
            
        pages = {
            "📈 市场情绪": "市场情绪",
            "🔬 情绪深度分析": "情绪深度分析",
            "🌪️ 题材共振": "题材共振",
            "🔬 题材深度分析": "题材深度分析",
            "🔥 涨停分析": "涨停分析",
            "🏆 个股趋势": "个股趋势"
        }
        
        for label, p_name in pages.items():
            if st.button(label, use_container_width=True, 
                         type="primary" if st.session_state.current_page == p_name else "secondary"):
                st.session_state.current_page = p_name
                st.rerun()
        
        st.markdown("---")
        
        # 4. 数据刷新控制
        st.subheader("🔄 数据刷新")
        if st.button("🧹 清除缓存并刷新", use_container_width=True, type="secondary"):
            # 清除服务层内存缓存
            market_service.clear_memory_cache()
            print("🧹 服务层内存缓存已清除")
            # 清除Streamlit数据缓存
            st.cache_data.clear()
            print("🧹 Streamlit缓存已清除")
            st.success("缓存已清除，页面将刷新...")
            st.rerun()

        # 调试：显示缓存状态
        cache_info = market_service.cache.info()
        st.caption(f"缓存: {cache_info['count']} 项")
        
        st.markdown("---")
        


    # 当前确定的日期和字符串
    target_dt = st.session_state.selected_date
    date_str = target_dt.strftime('%Y-%m-%d')
    page = st.session_state.current_page

    # --- 主界面路由分发 ---
    
    # 场景 1: 市场情绪
    if page == "市场情绪":
        valid_dates = [d for d in all_dates if d <= target_dt][-40:]
        with st.spinner("加载趋势中..."):
            df_trend = get_sentiment_data(tuple(valid_dates))
            render_sentiment_dashboard(df_trend)
    
    # 场景 1.5: 情绪深度分析
    elif page == "情绪深度分析":
        render_sentiment_analysis_deep()

    # 场景 2: 个股趋势 (修复点：找回 Top15 计算与渲染逻辑)
    elif page == "个股趋势":
        st.subheader(f"🏆 Top15 个股趋势分析 ({date_str})")

        # 调用服务层获取数据（服务层会自动触发计算）
        df_top15 = market_service.get_top15_data(target_dt, trend_days=30)
        
        if df_top15.empty:
            st.warning("⚠️ 暂无Top15数据")
        else:
            # 区分竞价和收盘数据
            df_auc = df_top15[df_top15['类型'] == '竞价'].copy()
            df_cls = df_top15[df_top15['类型'] == '收盘'].copy()
            
            # 判断数据完整性
            has_auc = not df_auc.empty
            has_cls = not df_cls.empty
            
            if has_auc and has_cls:
                # 完整数据
                render_top15_dashboard(df_auc, df_cls, target_date=target_dt)
            elif has_auc and not has_cls:
                # 只有竞价数据
                st.info("📊 只有竞价数据，收盘数据将在15:00后自动更新")
                render_top15_dashboard(df_auc, df_cls, target_date=target_dt)
            elif not has_auc and has_cls:
                # 只有收盘数据（异常情况）
                st.warning("⚠️ 缺少竞价数据")
                render_top15_dashboard(df_auc, df_cls, target_date=target_dt)
            else:
                st.warning("⚠️ 暂无Top15数据")

    # 场景 3: 涨停分析
    elif page == "涨停分析":
        col_auction, col_close = st.columns(2)
        df_close = None
        target_dt_close = None
        
        with col_auction:
            st.markdown("#### 🚀 竞价阶段")
            res_auc = market_service.get_limit_up_data(target_dt, stage="竞价")
            if res_auc.status == DataStatus.OK:
                render_zhangting_dashboard(res_auc.data, analyze_zhangting_stats(res_auc.data), target_date=target_dt, stage="竞价")
            else:
                st.info("⏳ 竞价数据尚未生成")
        
        with col_close:
            st.markdown("#### 🏁 收盘阶段")
            res_close = market_service.get_limit_up_data(target_dt, stage="收盘")
            if res_close.status == DataStatus.OK:
                df_close = res_close.data
                target_dt_close = target_dt
                render_zhangting_dashboard(df_close, analyze_zhangting_stats(df_close), target_date=target_dt_close, stage="收盘", show_concept=False)
            else:
                st.info("⏳ 收盘数据尚未生成")
        
        if df_close is not None:
            st.markdown("---")
            st.markdown("#### 📊 收盘阶段深度分析")
            render_concept_analysis_tables(df_close, target_dt_close)

    # 场景 4: 题材共振
    elif page == "题材共振":
        render_concept_dashboard(target_dt)
    
    # 场景 6: 题材深度分析
    elif page == "题材深度分析":
        render_concept_analysis_deep(target_dt)

if __name__ == "__main__":
    main()
