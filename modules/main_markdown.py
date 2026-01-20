import streamlit as st
import io
import contextlib
import pandas as pd
from datetime import datetime
from modules.config import SAVE_DIR
from modules.data_loader import get_trade_dates
from modules.analyzer import (
    analyze_auction_flow, calculate_hot_concepts, calculate_auto_concepts, build_zt_tags
)
from modules.reporter import (
    report_overview, report_top_stocks, report_sector_flow, report_top_amount_stocks,
    report_hot_concepts, report_auto_concepts, report_zt_stocks
)

def render_auction_report_tab(selected_date=None, prev_date=None):
    """
    支持外部传入日期，实现与侧边栏联动
    """
    st.header("📊 每日竞价深度分析报告")
    
    # 获取日期逻辑修复
    date_list = get_trade_dates(30)
    if not date_list or len(date_list) < 2:
        st.error("❌ 无法获取交易日期数据")
        return

    # 优先使用外部传入的日期，如果没有(直接运行脚本时)则取最新的
    if selected_date is None:
        today_date = date_list[-1]
        prev_date = date_list[-2]
    else:
        today_date = selected_date
        # 如果没传 prev_date，从列表中找选中日期的前一个
        if prev_date is None:
            try:
                idx = date_list.index(today_date)
                prev_date = date_list[idx-1]
            except:
                prev_date = date_list[-2]

    # 在界面显示当前锁定的分析日期
    st.info(f"📅 当前分析：{today_date.strftime('%Y-%m-%d')} (对比日：{prev_date.strftime('%Y-%m-%d')})")
    
    # 按钮控制
    if st.button("🚀 生成/刷新今日深度报告", use_container_width=True):
        if not today_date:
            st.error("❌ 无法获取有效交易日")
            return

        with st.spinner(f"正在深度分析 {today_date.strftime('%Y-%m-%d')} 数据..."):
            try:
                # 1. 执行核心分析逻辑
                result = analyze_auction_flow(today_date, prev_date)
                if result is None:
                    st.warning("⚠️ 竞价行情数据尚未下载，请先执行抓取。")
                    return

                df, overview = result
                
                # --- 关键修复：获取并合并“热点标签” ---
                # 提前构建涨停/热点标签
                df_zt = build_zt_tags(today_date, prev_date)
                
                # 将标签合并进主表 df，防止后续 reporter 找不到列
                if not df_zt.empty and '热点标签' in df_zt.columns:
                    # 仅选取代码和标签列进行左连接
                    tag_slice = df_zt[['股票代码', '热点标签']].drop_duplicates('股票代码')
                    df = pd.merge(df, tag_slice, on='股票代码', how='left')
                    df['热点标签'] = df['热点标签'].fillna('')
                else:
                    df['热点标签'] = '' # 兜底，防止列缺失
                # --- 修复结束 ---

                # 2. 计算其他题材数据
                total_abs = df['增量(亿)'].abs().sum()
                hot_concept_stats = calculate_hot_concepts(df)
                auto_concept_df = calculate_auto_concepts(df)

                # 3. 核心改进：捕获 print 输出并转换为 Markdown
                output_buffer = io.StringIO()
                with contextlib.redirect_stdout(output_buffer):
                    report_overview(today_date, prev_date, overview)
                    # 现在 df 包含‘热点标签’，调用 report_top_amount_stocks 不再报错
                    report_top_amount_stocks(df, top_n=12)
                    report_top_stocks(df)
                    report_sector_flow(df, total_abs)
                    report_hot_concepts(hot_concept_stats)
                    report_auto_concepts(auto_concept_df, top_n=10)
                    report_zt_stocks(today_date, prev_date, df_zt)
                
                report_md_content = output_buffer.getvalue()

                # 4. Streamlit 页面渲染展示
                st.success(f"✅ 分析完成！(报告生成时间：{datetime.now().strftime('%H:%M:%S')})")

                # --- 题材亮点区 ---
                tab_hot, tab_auto = st.tabs(["🔥 热门题材统计", "🤖 智能题材挖掘"])
                
                with tab_hot:
                    st.dataframe(hot_concept_stats, use_container_width=True)
                
                with tab_auto:
                    st.dataframe(auto_concept_df, use_container_width=True)

                # --- 完整 Markdown 内容展示 ---
                st.divider()
                st.subheader("📝 完整报告正文")
                with st.container(border=True):
                    st.markdown(report_md_content)

                # --- 提供导出功能 ---
                st.download_button(
                    label="📥 下载报告 (.md)",
                    data=report_md_content,
                    file_name=f"竞价分析_{today_date.strftime('%Y%m%d')}.md",
                    mime="text/markdown"
                )

            except Exception as e:
                st.error(f"❌ 分析出错: {e}")
                st.exception(e)

# 保持兼容性
if __name__ == "__main__":
    st.set_page_config(layout="wide")
    render_auction_report_tab()
    
