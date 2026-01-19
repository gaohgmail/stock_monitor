# -*- coding: utf-8 -*-

import sys
import os
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

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

# --- 2. 核心逻辑函数 ---

def analyze_daily_sentiment(df_today: pd.DataFrame, prefix: str = "竞价"):
    """
    通用计算逻辑：支持竞价和收盘数据的动态切换
    """
    if df_today.empty: 
        return {}

    # 定义动态列名
    amt_col = f"{prefix}金额"
    price_col = f"{prefix}价"

    # 1. 基础金额统计 (亿元)
    total_amt = df_today[amt_col].sum() / 1e8
    sh_amt = df_today[df_today['股票代码'].str.startswith('sh6')][amt_col].sum() / 1e8
    cyb_amt = df_today[df_today['股票代码'].str.startswith('sz3')][amt_col].sum() / 1e8

    # 2. 情绪指标统计 (过滤 ST)
    mask_not_st = ~df_today['股票简称'].str.contains('ST|st', na=False)
    t = df_today[mask_not_st].copy()
    t_sh = t[t['股票代码'].str.startswith('sh6')]
    t_cyb = t[t['股票代码'].str.startswith('sz3')]

    # 3. 涨跌停判定
    is_limit_up = (t[price_col] > 0) & (abs(t[price_col] - t['涨停价']) < 0.01)
    is_limit_down = (t[price_col] > 0) & (abs(t[price_col] - t['跌停价']) < 0.01)

    # 4. 构建结果字典
    raw_stats = {
        '总额': total_amt,
        '上海额': sh_amt,
        '创业额': cyb_amt,
        '强力': (t['涨跌幅'] >= 7).sum(),
        '极弱': (t['涨跌幅'] <= -7).sum(),
        '涨停': is_limit_up.sum(),
        '跌停': is_limit_down.sum(),
        '上涨数': (t['涨跌幅'] > 0).sum(),
        '下跌数': (t['涨跌幅'] < 0).sum(),
        '沪涨': (t_sh['涨跌幅'] > 0).sum(),
        '沪跌': (t_sh['涨跌幅'] < 0).sum(),
        '创涨': (t_cyb['涨跌幅'] > 0).sum(),
        '创跌': (t_cyb['涨跌幅'] < 0).sum()
    }
    return {f"{prefix}_{k}": v for k, v in raw_stats.items()}

@st.cache_data
def get_sentiment_trend_report(date_list: list):
    """
    批量处理日期序列，生成趋势 DataFrame
    """
    daily_results = []
    for d in date_list:
        df_jj = read_market_data(d, '竞价行情')
        df_sp = read_market_data(d, '收盘行情')
        
        if df_jj.empty and df_sp.empty: 
            continue
        
        res_jj = analyze_daily_sentiment(df_jj, prefix="竞价") if not df_jj.empty else {}
        res_sp = analyze_daily_sentiment(df_sp, prefix="收盘") if not df_sp.empty else {}
        
        combined = {'日期': d.strftime('%Y-%m-%d')}
        combined.update(res_jj)
        combined.update(res_sp)
        daily_results.append(combined)

    trend_df = pd.DataFrame(daily_results)
    if trend_df.empty: 
        return trend_df
    
    trend_df = trend_df.sort_values('日期') 

    # 衍生成交额与涨跌比
    for p in ['竞价', '收盘']:
        main_col = f'{p}_总额'
        if main_col not in trend_df.columns:
            continue
            
        trend_df[f'{p}_资金增减'] = trend_df[main_col].diff()
        trend_df[f'{p}_增减幅'] = trend_df[main_col].pct_change()
        
        if f'{p}_上海额' in trend_df.columns:
            trend_df[f'{p}_上海差值'] = trend_df[f'{p}_上海额'].diff()
        if f'{p}_创业额' in trend_df.columns:
            trend_df[f'{p}_创业差值'] = trend_df[f'{p}_创业额'].diff()

        if f'{p}_上涨数' in trend_df.columns:
            trend_df[f'{p}_全场涨跌比'] = trend_df[f'{p}_上涨数'] / trend_df[f'{p}_下跌数'].replace(0, 1)
        if f'{p}_沪涨' in trend_df.columns:
            trend_df[f'{p}_上海涨跌比'] = trend_df[f'{p}_沪涨'] / trend_df[f'{p}_沪跌'].replace(0, 1)
        if f'{p}_创涨' in trend_df.columns:
            trend_df[f'{p}_创业涨跌比'] = trend_df[f'{p}_创涨'] / trend_df[f'{p}_创跌'].replace(0, 1)

        # 新增：涨跌停与强弱每日差值（用于界面下标/Delta 显示）
        if f'{p}_涨停' in trend_df.columns:
            trend_df[f'{p}_涨停_diff'] = trend_df[f'{p}_涨停'].diff().fillna(0).astype(int)
        if f'{p}_跌停' in trend_df.columns:
            trend_df[f'{p}_跌停_diff'] = trend_df[f'{p}_跌停'].diff().fillna(0).astype(int)
        if f'{p}_强力' in trend_df.columns:
            trend_df[f'{p}_强力_diff'] = trend_df[f'{p}_强力'].diff().fillna(0).astype(int)
        if f'{p}_极弱' in trend_df.columns:
            trend_df[f'{p}_极弱_diff'] = trend_df[f'{p}_极弱'].diff().fillna(0).astype(int)

    return trend_df

# --- 3. UI 渲染函数 ---

def render_dashboard(df: pd.DataFrame):
    st.title("📊 市场情绪监控系统 (竞价 vs 收盘)")
    
    if df.empty:
        st.warning("暂无交易数据，请检查数据源。")
        return

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    # --- 1. 竞价指标区 (增加上海/创业板显示) ---
    st.subheader("🚀 竞价核心情绪")
    # 这里改成了 6 列，把你要加的内容塞进去
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric("竞价总额", f"{latest['竞价_总额']:.2f} 亿", delta=f"{latest['竞价_资金增减']:.2f} 亿")
    with col2:
        st.metric("全场涨跌比", f"{latest['竞价_全场涨跌比']:.2f}", 
                  delta=f"{latest['竞价_全场涨跌比'] - prev['竞价_全场涨跌比']:.2f}")
    with col3:
        # 新增：上海竞价细节
        st.metric("上海涨跌比", f"{latest.get('竞价_上海涨跌比', 0):.2f}", 
                  delta=f"{latest.get('竞价_上海差值', 0):+.2f} 亿")
    with col4:
        # 新增：创业板竞价细节
        st.metric("创业涨跌比", f"{latest.get('竞价_创业涨跌比', 0):.2f}", 
                  delta=f"{latest.get('竞价_创业差值', 0):+.2f} 亿")
    with col5:
        up = int(latest.get('竞价_涨停', 0))
        down = int(latest.get('竞价_跌停', 0))
        up_diff = int(latest.get('竞价_涨停_diff', 0))
        down_diff = int(latest.get('竞价_跌停_diff', 0))
        st.metric("竞价涨/跌停", f"{up} / {down}", delta=f"{up_diff:+d} / {down_diff:+d}")
    with col6:
        strong = int(latest.get('竞价_强力', 0))
        weak = int(latest.get('竞价_极弱', 0))
        s_diff = int(latest.get('竞价_强力_diff', 0))
        w_diff = int(latest.get('竞价_极弱_diff', 0))
        st.metric("竞价强力|弱力", f"{strong}  / {weak}", delta=f"{s_diff:+d}  / {w_diff:+d}")

    # --- 2. 收盘指标区 (同样增加上海/创业板显示) ---
    if '收盘_总额' in df.columns and not pd.isna(latest['收盘_总额']):
        st.divider()
        st.subheader("🏁 收盘核心情绪")
        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
        
        with sc1:
            st.metric("收盘总额", f"{latest['收盘_总额']:.2f} 亿", delta=f"{latest['收盘_资金增减']:.2f} 亿")
        with sc2:
            repair = latest['收盘_全场涨跌比'] - latest['竞价_全场涨跌比']
            st.metric("收盘涨跌比", f"{latest['收盘_全场涨跌比']:.2f}", delta=f" {repair:.2f}盘中")
        with sc3:
            # 新增：上海收盘细节
            st.metric("上海涨跌比", f"{latest.get('收盘_上海涨跌比', 0):.2f}", 
                      delta=f"{latest.get('收盘_上海差值', 0):+.2f} 亿")
        with sc4:
            # 新增：创业板收盘细节
            st.metric("创业涨跌比", f"{latest.get('收盘_创业涨跌比', 0):.2f}", 
                      delta=f"{latest.get('收盘_创业差值', 0):+.2f} 亿")
        with sc5:
            up = int(latest.get('收盘_涨停', 0))
            down = int(latest.get('收盘_跌停', 0))
            up_diff = int(latest.get('收盘_涨停_diff', 0))
            down_diff = int(latest.get('收盘_跌停_diff', 0))
            st.metric("收盘涨/跌停", f"{up} / {down}", delta=f"{up_diff:+d} / {down_diff:+d}")
        with sc6:
            strong = int(latest.get('收盘_强力', 0))
            weak = int(latest.get('收盘_极弱', 0))
            s_diff = int(latest.get('收盘_强力_diff', 0))
            w_diff = int(latest.get('收盘_极弱_diff', 0))
            st.metric("收盘强力|弱力", f"{strong}  / {weak}", delta=f"{s_diff:+d}  / {w_diff:+d}")
    else:
        st.info("💡 当前为早盘阶段，收盘数据尚未同步。")

    st.divider()

    # --- 3. 趋势图与表格部分保持你原来的代码不变 ---
    # (此处省略你原有的 Plotly 和 DataFrame 代码，直接接在后面即可)
    # ... [保持你发送的代码中趋势图和表格部分原封不动] ...

    # --- 趋势图 ---
    st.subheader("📈 趋势可视化 (金额与三线情绪共振)")
    mode = st.radio("切换趋势维度", ["竞价情绪趋势", "收盘情绪趋势"], horizontal=True)
    prefix = "竞价" if "竞价" in mode else "收盘"

    if f"{prefix}_总额" in df.columns:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=df['日期'], y=df[f'{prefix}_总额'], name="总额(亿)", marker_color='rgba(100, 149, 237, 0.6)'), secondary_y=False)
        fig.add_trace(go.Scatter(x=df['日期'], y=df[f'{prefix}_全场涨跌比'], name="全场涨跌比", line=dict(color='firebrick', width=3)), secondary_y=True)
        fig.add_trace(go.Scatter(x=df['日期'], y=df[f'{prefix}_创业涨跌比'], name="创业板涨跌比", line=dict(color='royalblue', width=2, dash='dot')), secondary_y=True)

        fig.update_layout(
    height=500, 
    hovermode="x unified",
    # 核心修改：将图例放在图表正下方（居中），不占用左右空间
    legend=dict(
        orientation="h",   # 水平排列
        yanchor="bottom",  # 底部对齐
        y=1.05,            # 放在 Y 轴 0 点以下（即图表下方）
        xanchor="center",  # 锚点设在中间
        x=0.5              # 放在画布 50% 的位置
    ),
    # 减少四周留白，让图表主体更大
    margin=dict(l=10, r=10, t=50, b=10)
)

        # 记得加上这一行，解决你截图中柱子太细的问题
        fig.update_xaxes(type='category')

        # 提供合并并排显示选项：勾选后原图与合并图并排显示（左右两列）
        show_combined = st.checkbox("并排显示：合并图（竞价/收盘 资金增减 + 涨跌比）", value=False)

        if show_combined:
            # 构建合并图（同一张图内展示资金增减与涨跌比）
            fig2 = make_subplots(specs=[[{"secondary_y": True}]])

            if '竞价_资金增减' in df.columns:
                fig2.add_trace(go.Bar(x=df['日期'], y=df['竞价_资金增减'], name='竞价资金增减(亿)', marker_color='rgba(55, 128, 191, 0.7)'), secondary_y=False)
            if '收盘_资金增减' in df.columns:
                fig2.add_trace(go.Bar(x=df['日期'], y=df['收盘_资金增减'], name='收盘资金增减(亿)', marker_color='rgba(26, 118, 255, 0.5)'), secondary_y=False)

            if '竞价_全场涨跌比' in df.columns:
                fig2.add_trace(go.Scatter(x=df['日期'], y=df['竞价_全场涨跌比'], name='竞价涨跌比', mode='lines+markers', line=dict(color='firebrick', width=2)), secondary_y=True)
            if '收盘_全场涨跌比' in df.columns:
                fig2.add_trace(go.Scatter(x=df['日期'], y=df['收盘_全场涨跌比'], name='收盘涨跌比', mode='lines+markers', line=dict(color='royalblue', width=2, dash='dot')), secondary_y=True)

            fig2.update_layout(title_text=f"合并：资金增减(亿) 与 涨跌比", height=500, hovermode='x unified', barmode='group', legend=dict(orientation='h', yanchor='bottom', y=1.05, xanchor='center', x=0.5), margin=dict(l=10, r=10, t=60, b=10))
            fig2.update_xaxes(type='category')
            fig2.update_yaxes(title_text='资金增减 (亿)', secondary_y=False)
            fig2.update_yaxes(title_text='涨跌比', secondary_y=True)

            left_col, right_col = st.columns(2)
            left_col.plotly_chart(fig, use_container_width=True)
            right_col.plotly_chart(fig2, use_container_width=True)
        else:
            st.plotly_chart(fig, use_container_width=True)

    # --- 数据表格 ---
    st.subheader("📋 详细统计数据")
    cols = ['日期', f'{prefix}_总额', f'{prefix}_资金增减', f'{prefix}_全场涨跌比', f'{prefix}_强力', f'{prefix}_极弱', f'{prefix}_涨停', f'{prefix}_跌停']
    valid_cols = [c for c in cols if c in df.columns]
    
    st.dataframe(
        df[valid_cols].sort_values('日期', ascending=False).style.format({
            f'{prefix}_总额': "{:.2f}", f'{prefix}_资金增减': "{:+.2f}", f'{prefix}_全场涨跌比': "{:.2f}"
        }).background_gradient(subset=[f'{prefix}_全场涨跌比'], cmap='RdYlGn'),
        use_container_width=True
    )

    # --- 原始数据表格 (放在详细统计数据下方) ---
    with st.expander("🔍 查看原始数据明细"):
        st.write("以下为未经过格式化处理的原始 CSV 记录：")
        # 直接显示原始 dataframe，不带样式，支持搜索、排序和下载 CSV
        st.dataframe(
            df.sort_values('日期', ascending=False), 
            use_container_width=True
        )

    # --- 新增交互绘图：用户可选择列并自定义图表类型与颜色 ---
    st.markdown("---")
    st.subheader("📊 自定义绘图")

    # 可选的绘图列：直接使用原始 DataFrame 的列（排除日期列用于 y 轴选择）
    plot_columns_options = [c for c in df.columns if c != '日期']

    if not plot_columns_options:
        st.info("当前没有可绘制的列。")
    else:
        cols_to_plot = st.multiselect("选择要绘制的列（可多选）", plot_columns_options, default=plot_columns_options[:1])

        # 每列单独配置：颜色 + 图表类型（横向显示）
        palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
        colors = {}
        types = {}
        axis_map = {}
        for i, colname in enumerate(cols_to_plot):
            default_color = palette[i % len(palette)]
            a, b, c = st.columns([1, 1, 1])
            with a:
                colors[colname] = st.color_picker(f"{colname} 颜色", value=default_color, key=f"color_{colname}")
            with b:
                types[colname] = st.selectbox(f"{colname} 类型", ["折线图", "柱状图"], index=0, key=f"type_{colname}")
            with c:
                axis_choice = st.selectbox(f"{colname} 轴", ["主轴", "次轴"], index=0, key=f"axis_{colname}")
                axis_map[colname] = axis_choice

        if cols_to_plot:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            x = df['日期'] if '日期' in df.columns else df.index

            for colname in cols_to_plot:
                if colname not in df.columns:
                    continue
                y = df[colname]
                c = colors.get(colname, palette[0])
                t = types.get(colname, '折线图')
                use_secondary = (axis_map.get(colname) == '次轴')

                if t == '柱状图':
                    fig.add_trace(go.Bar(x=x, y=y, name=colname, marker_color=c), secondary_y=use_secondary)
                else:
                    fig.add_trace(go.Scatter(x=x, y=y, name=colname, mode='lines+markers', line=dict(color=c)), secondary_y=use_secondary)

            fig.update_layout(height=550, hovermode='x unified', legend=dict(orientation='h', x=0.5, xanchor='center'))
            fig.update_xaxes(type='category')
            st.plotly_chart(fig, use_container_width=True)

            # 提供导出图片/CSV 的快捷按钮
            with st.expander("导出/下载"):
                if st.button("下载图表为 PNG"):
                    try:
                        buf = fig.to_image(format='png')
                        st.download_button("点击下载 PNG", data=buf, file_name='chart.png', mime='image/png')
                    except Exception as e:
                        st.error(f"导出图片失败: {e}")

                if st.button("下载所选列为 CSV"):
                    try:
                        csv_buf = df[[ '日期' ] + cols_to_plot].to_csv(index=False, encoding='utf-8')
                        st.download_button("点击下载 CSV", data=csv_buf, file_name='data.csv', mime='text/csv')
                    except Exception as e:
                        st.error(f"导出 CSV 失败: {e}")


# --- 新增：身份验证函数 ---
import socket

def check_password():
    """检测访问环境：本机/局域网免密，外网需密码"""
    
    # 1. 获取访问者的 IP 地址
    # 在 Streamlit 中，远程访问者的 IP 通常存在于 headers 中
    headers = st.context.headers
    # 获取客户端 IP (考虑到可能经过代理，优先获取 x-forwarded-for)
    client_ip = headers.get("x-forwarded-for", "127.0.0.1").split(",")[0]

    # 2. 定义白名单（本机和常见的局域网段）
    # 127.0.0.1 是本机，192.168. 是常见的家里/办公室路由器网段
    is_local = (
        client_ip == "127.0.0.1" or 
        client_ip == "localhost" or 
        client_ip.startswith("192.168.") or 
        client_ip.startswith("172.") or
        client_ip.startswith("10.")
    )

    # 3. 如果是本机或局域网，直接放行
    if is_local:
        return True

    # 4. 如果是外网访问（cpolar 穿透进来的），则执行原有的密码校验逻辑
    def password_entered():
        if st.session_state["password"] == "888888oooo42":  # <-- 这里改回你的密码
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🛡️ 远程访问受限，请输入密码", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("❌ 密码错误，请重新输入", type="password", on_change=password_entered, key="password")
        return False
    else:
        return True

import subprocess


def run_data_download_script():
    try:
        # 获取当前文件的绝对路径，确保定位到 main.py
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_dir, "main.py")
        
        # 【核心修改】：使用 sys.executable 而不是 "python"
        # sys.executable 会直接指向当前已经装好 pandas 的那个 Python 解释器
        result = subprocess.run(
            [sys.executable, script_path], 
            capture_output=True, 
            text=True,
            encoding='utf-8'
        )
        
        if result.returncode == 0:
            return True, "数据更新成功！"
        else:
            # 这里的 stderr 会捕捉到 main.py 内部的报错
            return False, f"更新失败: {result.stderr}"
    except Exception as e:
        return False, f"程序异常: {str(e)}"
# --- 4. 运行入口 ---
if __name__ == "__main__":
    # A. 页面基础配置 (必须是第一个 Streamlit 命令)
    st.set_page_config(page_title="市场情绪监控系统", layout="wide")

    # B. 安全校验：只有通过密码验证才显示内容
    if check_password():
        
        # 1. 核心数据载入 (一次载入，全局共用)
        LOOKBACK_DAYS = 30
        trade_dates = get_trade_dates(LOOKBACK_DAYS)
        report_df = get_sentiment_trend_report(trade_dates)

        # 检查数据是否为空
        if report_df.empty:
            st.error("❌ 数据加载失败，请检查 CSV 文件路径及内容。")
            st.stop()

        # 2. 侧边栏：放置控制功能
        with st.sidebar:
            st.header("⚙️ 系统控制")
            
            # --- 日期筛选功能 ---
            # 将日期列转换为 datetime 格式以获取范围
            all_dates = pd.to_datetime(report_df['日期']).dt.date
            min_date = all_dates.min()
            max_date = all_dates.max()
            
            st.subheader("📅 日期筛选")
            target_date = st.date_input(
                "选择看板显示日期", 
                value=max_date,  # 默认显示最新一天
                min_value=min_date,
                max_value=max_date
            )
            # 转回字符串用于数据定位
            target_date_str = target_date.strftime('%Y-%m-%d')
            st.caption(f"📍 当前查看: {target_date_str}")

            st.markdown("---")
            
            # 按钮 1：执行外部抓取脚本
            if st.button("🚀 抓取今日 9:25 数据", use_container_width=True):
                with st.spinner("正在远程执行抓取脚本..."):
                    success, msg = run_data_download_script()
                    if success:
                        st.cache_data.clear() # 清理缓存以读取新抓取的文件
                        st.success(msg)
                        st.balloons()
                    else:
                        st.error(msg)

            # 按钮 2：刷新当前显示
            if st.button("🔄 同步最新数据", use_container_width=True):
                st.cache_data.clear()
                st.rerun() # 强制界面重绘
            
            st.markdown("---")
            st.write(f"📊 回溯跨度：{LOOKBACK_DAYS} 个交易日")
            st.write(f"⏰ 刷新时间：{datetime.now().strftime('%H:%M:%S')}")

        # 3. 数据切片逻辑：根据用户选中的日期决定展示内容
        # 找到选中日期在 DataFrame 中的索引位置
        selected_indices = report_df[report_df['日期'] == target_date_str].index.tolist()
        
        if selected_indices:
            # 取得选定日期的位置索引
            idx = selected_indices[0]
            
            # 【核心技巧】：截取 0 到 idx 的数据
            # 这样 render_dashboard 里的 .iloc[-1] 就是你选的那天
            # .iloc[-2] 就是那天之前的一个交易日，用于计算增长差值
            display_df = report_df.loc[:idx] 
            
            # 4. 执行渲染：将处理后的数据传给主看板函数
            render_dashboard(display_df)
        else:
            st.error(f"⚠️ 在记录中未找到 {target_date_str} 的历史数据。")





