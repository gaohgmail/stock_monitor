# -*- coding: utf-8 -*-
"""
调度器模块
负责后台定时任务的调度和管理
支持单例模式、文件锁、跨平台兼容
"""

import atexit
import os
import random
import signal
import subprocess
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from tools.config import CALENDAR_PATH, METADATA_DIR, SCHEDULED_JOBS, SCHEDULER_STATUS_PATH

warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')

# 全局调度器实例（确保只启动一次）
_scheduler_instance = None
_scheduler_initialized = False
_scheduler_pid = None


def is_trade_day():
    """判定今天是否为交易日"""
    try:
        if not CALENDAR_PATH.exists(): 
            return True 
        df_cal = pd.read_csv(CALENDAR_PATH)
        date_col = next((c for c in df_cal.columns if any(x in c.lower() for x in ['date', '日期'])), df_cal.columns[0])
        today_str = datetime.now().strftime('%Y-%m-%d')
        return today_str in df_cal[date_col].values.astype(str)
    except:
        return True


def _write_log(message):
    """静默写入日志文件"""
    try:
        with open(SCHEDULER_STATUS_PATH, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except: 
        pass


def _get_lock_file_path():
    """获取锁文件路径"""
    lock_dir = METADATA_DIR / 'locks'
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / 'scheduler.lock'


def _read_lock_file():
    """读取锁文件，返回PID和创建时间"""
    lock_file = _get_lock_file_path()
    if not lock_file.exists():
        return None, None
    
    try:
        with open(lock_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return None, None
            
            parts = content.split(',')
            if len(parts) >= 2:
                try:
                    pid = int(parts[0].strip())
                    timestamp = float(parts[1].strip())
                    return pid, timestamp
                except (ValueError, IndexError):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 锁文件格式错误: {content}")
                    return None, None
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 读取锁文件失败: {e}")
    
    return None, None


def _write_lock_file(pid):
    """写入锁文件，包含PID和当前时间戳"""
    lock_file = _get_lock_file_path()
    try:
        timestamp = time.time()
        content = f"{pid},{timestamp}"
        
        # 先写入临时文件，然后重命名，确保原子性
        temp_file = lock_file.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 重命名临时文件为正式文件
        temp_file.replace(lock_file)
        
        return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 写入锁文件失败: {e}")
        return False


def _is_process_running(pid):
    """检查指定PID的进程是否还在运行"""
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    
    # 使用平台相关的方法
    try:
        if sys.platform == 'win32':
            # Windows平台使用tasklist命令
            result = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}', '/NH', '/FO', 'CSV'],
                capture_output=True, text=True, timeout=5
            )
            # 检查输出中是否包含该PID
            output = result.stdout.strip()
            if output and not output.startswith('信息'):
                # 解析CSV格式输出
                parts = output.split(',')
                if len(parts) >= 2:
                    try:
                        found_pid = int(parts[1].strip('"'))
                        return found_pid == pid
                    except ValueError:
                        pass
            return False
        else:
            # Unix-like系统使用os.kill(pid, 0)
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def _try_acquire_lock():
    """尝试获取调度器锁"""
    lock_file = _get_lock_file_path()
    try:
        # 读取锁文件中的PID和时间戳
        pid, timestamp = _read_lock_file()
        current_pid = os.getpid()
        
        # 如果锁文件中的PID就是当前进程的PID，说明当前进程已经启动了调度器
        if pid is not None and pid == current_pid:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 当前进程已持有锁 (PID: {current_pid})")
            return True
        
        if pid is not None and timestamp is not None:
            # 检查锁文件是否在1小时内创建
            if time.time() - timestamp < 3600:  # 1小时内
                # 检查该PID的进程是否还在运行
                if _is_process_running(pid):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 检测到已有调度器在运行 (PID: {pid})")
                    return False
                else:
                    # 进程不存在，清理锁文件
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧹 检测到旧锁文件，进程已终止 (PID: {pid})")
                    try:
                        lock_file.unlink()
                    except Exception as e:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 清理旧锁文件失败: {e}")
                        return False
            else:
                # 锁文件超过1小时，视为过期，清理
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧹 检测到过期锁文件，自动清理")
                try:
                    lock_file.unlink()
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 清理过期锁文件失败: {e}")
                    return False
        
        # 创建/更新锁文件
        if _write_lock_file(current_pid):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔒 创建锁文件 (PID: {current_pid})")
            return True
        return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 锁文件操作失败: {e}")
        return True  # 出错时允许继续，避免阻塞


def _cleanup_scheduler():
    """清理调度器和锁文件"""
    global _scheduler_instance, _scheduler_initialized, _scheduler_pid
    
    current_pid = os.getpid()
    
    # 只有持有锁的进程才执行清理
    lock_pid, _ = _read_lock_file()
    if lock_pid != current_pid:
        return
    
    try:
        # 停止调度器
        if _scheduler_instance is not None:
            if _scheduler_instance.running:
                _scheduler_instance.shutdown(wait=False)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 调度器已停止")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ℹ️ 调度器未运行")
        
        # 清理锁文件
        lock_file = _get_lock_file_path()
        if lock_file.exists():
            try:
                lock_file.unlink()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧹 锁文件已清理")
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 清理锁文件失败: {e}")
        
        # 清理临时锁文件
        temp_lock_file = lock_file.with_suffix('.tmp')
        if temp_lock_file.exists():
            try:
                temp_lock_file.unlink()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧹 临时锁文件已清理")
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 清理临时锁文件失败: {e}")
        
        # 重置全局变量
        _scheduler_instance = None
        _scheduler_initialized = False
        _scheduler_pid = None
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 清理失败: {e}")


def run_job(script_name, task_label):
    """带资源保护、编码加固和路径容错的后台执行函数"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 任务开始时先记录日志
    _write_log(f"{task_label}|{timestamp}|开始执行...")
    
    # 资源保护：随机延迟 1-5 秒，防止多个任务瞬间并发挤爆虚拟内存 (页面文件太小报错)
    time.sleep(random.uniform(1, 5))

    if not is_trade_day():
        _write_log(f"{task_label}|{timestamp}|跳过: 非交易日")
        return

    try:
        # sys.executable 自动处理 Python 路径中的空格 (如 Program Files)
        interpreter = sys.executable
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.normpath(os.path.join(base_dir, script_name))
        
        # 检查脚本文件是否存在
        if not os.path.exists(script_path):
            _write_log(f"{task_label}|{timestamp}|失败: 脚本文件不存在 - {script_path}")
            return
        
        # 强制子进程环境使用 UTF-8，解决 GBK 编码无法处理日志中特殊字符的报错
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [interpreter, script_path], 
            capture_output=True, text=True, cwd=base_dir, env=env,
            encoding='utf-8', errors='replace'
        )
        
        if result.returncode == 0:
            status = "成功"
        else:
            # 压平错误信息，截取前 200 字符防止日志过大
            error_msg = ' '.join(result.stderr.splitlines())[:200]
            if not error_msg:
                error_msg = ' '.join(result.stdout.splitlines())[:200]
            status = f"失败: {error_msg}"
        
        _write_log(f"{task_label}|{timestamp}|{status}")
            
    except FileNotFoundError as e:
        _write_log(f"{task_label}|{timestamp}|失败: Python解释器未找到 - {str(e)[:100]}")
    except PermissionError as e:
        _write_log(f"{task_label}|{timestamp}|失败: 权限不足 - {str(e)[:100]}")
    except subprocess.TimeoutExpired:
        _write_log(f"{task_label}|{timestamp}|失败: 脚本执行超时")
    except Exception as e:
        _write_log(f"{task_label}|{timestamp}|异常: {str(e)[:100]}")


def _check_scheduler_health(scheduler):
    """检查调度器健康状态"""
    if scheduler is None:
        return False
    try:
        if not scheduler.running:
            return False
        jobs = scheduler.get_jobs()
        if not jobs:
            return False
        return True
    except Exception:
        return False


def _force_cleanup_lock():
    """强制清理锁文件（无论PID是否匹配）"""
    lock_file = _get_lock_file_path()
    try:
        if lock_file.exists():
            lock_file.unlink()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧹 强制清理锁文件")
            return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 强制清理锁文件失败: {e}")
    return False


def init_scheduler(force_restart=False):
    """初始化后台调度器 (单例模式)
    
    Args:
        force_restart: 是否强制重启调度器（清理旧锁文件）
    """
    global _scheduler_instance, _scheduler_initialized, _scheduler_pid
    
    # 强制降低 APScheduler 的日志级别，防止报错刷屏
    import logging
    logging.getLogger('apscheduler').setLevel(logging.ERROR)
    
    current_pid = os.getpid()
    
    # ===== 自动重启检测：检查锁文件，如果进程已死则自动清理并重启 =====
    lock_pid, lock_time = _read_lock_file()
    if lock_pid is not None and not _is_process_running(lock_pid):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 检测到调度器进程已退出 (PID: {lock_pid})，自动清理并重启...")
        _force_cleanup_lock()
        _scheduler_initialized = False
        _scheduler_instance = None
    # ===== 自动重启检测结束 =====
    
    # 如果调度器已经初始化，检查其健康状态
    if _scheduler_initialized and _scheduler_instance is not None:
        if _scheduler_pid == current_pid:
            if _check_scheduler_health(_scheduler_instance):
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 调度器已存在且运行正常，跳过重复初始化")
                return _scheduler_instance
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 检测到调度器已停止，重新初始化")
                _scheduler_initialized = False
                _scheduler_instance = None
        else:
            # PID不同，说明是另一个进程启动的调度器，需要重新初始化
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 检测到PID变化 ({_scheduler_pid} -> {current_pid})，重新初始化")
            _scheduler_initialized = False
            _scheduler_instance = None
    
    # 强制重启模式：清理旧锁文件
    if force_restart:
        _force_cleanup_lock()
    
    # 尝试获取锁，防止多进程重复启动
    if not _try_acquire_lock():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 跳过调度器初始化（已有实例运行中）")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 💡 提示: 如需强制重启，可删除锁文件: {_get_lock_file_path()}")
        return None
    
    try:
        # 创建新的调度器实例
        scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        
        for job_id, info in SCHEDULED_JOBS.items():
            scheduler.add_job(
                run_job, CronTrigger(hour=info['time']['hour'], minute=info['time']['minute']),
                args=[info['script'], info['label']], id=job_id, replace_existing=True
            )
        
        scheduler.start()
        _scheduler_instance = scheduler
        _scheduler_initialized = True
        _scheduler_pid = current_pid
        
        # 记录启动信息到日志
        _write_log(f"调度器启动|{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}|PID:{current_pid}")
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 调度器已启动 (PID: {current_pid})")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📋 已注册任务:")
        for job_id, info in SCHEDULED_JOBS.items():
            print(f"   • {info['label']}: {info['time']['hour']:02d}:{info['time']['minute']:02d}")
        
        return scheduler
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 调度器启动失败: {e}")
        # 启动失败时清理锁文件
        _force_cleanup_lock()
        return None


def display_scheduler_status():
    """主界面 UI 渲染：显示最后一次任务的结果"""
    try:
        import streamlit as st
    except ImportError:
        print("警告: Streamlit未安装，无法显示调度器状态")
        return
    
    if not SCHEDULER_STATUS_PATH.exists(): 
        return
    try:
        with open(SCHEDULER_STATUS_PATH, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if "|" in l]
            if not lines: 
                return
            task_name, task_time, task_res = lines[-1].split("|")
            
            if "成功" in task_res:
                st.success(f"✅ **{task_name}** ({task_time}) 更新成功")
            elif "跳过" in task_res:
                st.info(f"🕒 **{task_name}** ({task_time}) 非交易日跳过")
            elif "调度器启动" in task_name and "PID" in task_res:
                st.success(f"🚀 **{task_name}** ({task_time}) 运行中")
            elif "调度器启动" in task_name:
                st.info(f"🚀 **{task_name}** ({task_time}) 已启动")
            else:
                with st.expander(f"❌ **{task_name}** ({task_time}) 运行失败"):
                    st.error(task_res)
    except: 
        pass

atexit.register(_cleanup_scheduler)


def _setup_signal_handlers():
    """
    尝试注册信号处理器。
    注意：Streamlit 脚本运行在子线程中，signal.signal 注册通常会失败。
    我们在这里通过静默处理来规避报错，主要依赖 atexit 和文件锁 PID 检测。
    """
    try:
        import threading
        if threading.current_thread() is threading.main_thread():
            def _handle_exit(signum, frame):
                _cleanup_scheduler()
                sys.exit(0)

            signal.signal(signal.SIGINT, _handle_exit)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, _handle_exit)
    except Exception:
        pass


_setup_signal_handlers()


def get_scheduler_if_running():
    """
    检测调度器是否正在运行（通过锁文件）
    返回调度器实例（如果在本进程）或 True（如果在其他进程）或 None（未运行）
    """
    global _scheduler_instance

    if _scheduler_instance is not None and _scheduler_initialized:
        return _scheduler_instance

    lock_file = _get_lock_file_path()
    if lock_file.exists():
        pid, _ = _read_lock_file()
        if pid is not None:
            try:
                import psutil
                if psutil.pid_exists(pid):
                    return True
            except ImportError:
                return True

    return None


print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛡️ 调度器监控已就绪 (依赖 atexit & PID 锁机制)")