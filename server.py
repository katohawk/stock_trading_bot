#!/usr/bin/env python3
"""
OKX 交易机器人 Web 控制台：启动/暂停、参数配置、实时日志、失败自动重试。
暗黑交易风前端 + Flask 后端，日志 SSE 推送。
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from flask import Flask, request, jsonify, Response, send_from_directory
except ImportError:
    print("请安装: pip install flask")
    sys.exit(1)

app = Flask(__name__, static_folder="web/static", static_url_path="")

# ---------- 进程与日志 ----------
process: subprocess.Popen = None
process_lock = threading.Lock()
log_queues: list = []
user_stopped = False
retry_count = 0
max_auto_retries = 5
retry_delay_sec = 10
retry_timer: threading.Timer = None

DEFAULT_PARAMS = {
    "symbol": "BTC/USDT",
    "ratio": 0.5,
    "interval": 60,
    "execute": False,
    "demo": False,
    "taker_fee_rate": 0.001,
    "buy_amount_usdt": 50.0,
    "min_buy_usdt": 10.0,
    "max_slippage": 0.001,
    "cooldown_sec": 60,
    "sell_fee_compensation_pct": 0.2,
    "exec_quality_threshold_pct": 0.1,
    "exec_pause_sec": 300,
}


def params_to_argv(params: dict) -> list:
    """将参数字典转为 run_okx_live.py 命令行参数."""
    cmd = [sys.executable, str(ROOT / "run_okx_live.py")]
    cmd += ["--symbol", str(params.get("symbol", "BTC/USDT"))]
    cmd += ["--ratio", str(params.get("ratio", 0.5))]
    cmd += ["--interval", str(params.get("interval", 60))]
    if params.get("execute"):
        cmd.append("--execute")
    if params.get("demo"):
        cmd.append("--demo")
    cmd += ["--taker-fee-rate", str(params.get("taker_fee_rate", 0.001))]
    cmd += ["--buy-amount-usdt", str(params.get("buy_amount_usdt", 50))]
    cmd += ["--min-buy-usdt", str(params.get("min_buy_usdt", 10))]
    cmd += ["--max-slippage", str(params.get("max_slippage", 0.001))]
    cmd += ["--cooldown-sec", str(params.get("cooldown_sec", 60))]
    cmd += ["--sell-fee-compensation-pct", str(params.get("sell_fee_compensation_pct", 0.2))]
    cmd += ["--exec-quality-threshold-pct", str(params.get("exec_quality_threshold_pct", 0.1))]
    cmd += ["--exec-pause-sec", str(params.get("exec_pause_sec", 300))]
    return cmd


def broadcast_log(line: str):
    for q in list(log_queues):
        try:
            q.put_nowait(line)
        except Exception:
            pass


def run_bot_worker(params: dict):
    """在子进程中运行机器人，并广播日志；退出后根据策略决定是否自动重试."""
    global process, retry_count, retry_timer, user_stopped
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    argv = params_to_argv(params)
    with process_lock:
        process = subprocess.Popen(
            argv,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    broadcast_log(f"[系统] 已启动: {' '.join(argv)}\n")
    try:
        for line in iter(process.stdout.readline, ""):
            broadcast_log(line)
    except Exception as e:
        broadcast_log(f"[系统] 读取输出异常: {e}\n")
    finally:
        code = process.poll()
        if code is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                process.kill()
            code = process.returncode
        with process_lock:
            process = None
        broadcast_log(f"[系统] 进程已退出，code={code}\n")
        if user_stopped:
            user_stopped = False
            return
        if code != 0 and retry_count < max_auto_retries:
            retry_count += 1
            broadcast_log(f"[系统] {retry_delay_sec} 秒后进行第 {retry_count}/{max_auto_retries} 次自动重试…\n")
            def retry_later():
                global retry_timer
                retry_timer = None
                run_bot_worker(params)
            retry_timer = threading.Timer(retry_delay_sec, retry_later)
            retry_timer.start()
        else:
            if retry_count >= max_auto_retries:
                broadcast_log(f"[系统] 已达最大自动重试次数 ({max_auto_retries})，停止重试。\n")
            retry_count = 0


current_params: dict = dict(DEFAULT_PARAMS)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/status")
def api_status():
    with process_lock:
        running = process is not None and process.poll() is None
    return jsonify({
        "running": running,
        "params": current_params,
        "retry_count": retry_count,
        "max_auto_retries": max_auto_retries,
    })


@app.route("/api/params", methods=["GET"])
def api_get_params():
    return jsonify(current_params)


@app.route("/api/params", methods=["POST"])
def api_set_params():
    global current_params
    data = request.get_json() or {}
    for k, v in DEFAULT_PARAMS.items():
        if k in data:
            if k in ("execute", "demo"):
                current_params[k] = bool(data[k])
            elif k in ("symbol",):
                current_params[k] = str(data[k]).strip() or DEFAULT_PARAMS[k]
            else:
                try:
                    current_params[k] = type(DEFAULT_PARAMS[k])(data[k])
                except (TypeError, ValueError):
                    pass
    return jsonify(current_params)


@app.route("/api/start", methods=["POST"])
def api_start():
    global current_params, retry_count, retry_timer, user_stopped
    data = request.get_json() or {}
    if data:
        for k, v in DEFAULT_PARAMS.items():
            if k in data:
                if k in ("execute", "demo"):
                    current_params[k] = bool(data[k])
                elif k == "symbol":
                    current_params[k] = str(data[k]).strip() or DEFAULT_PARAMS[k]
                else:
                    try:
                        current_params[k] = type(DEFAULT_PARAMS[k])(data[k])
                    except (TypeError, ValueError):
                        pass
    with process_lock:
        if process is not None and process.poll() is None:
            return jsonify({"ok": False, "message": "已在运行中"})
    user_stopped = False
    retry_count = 0
    if retry_timer:
        retry_timer.cancel()
        retry_timer = None
    t = threading.Thread(target=run_bot_worker, args=(dict(current_params),), daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "已启动"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global user_stopped, retry_timer
    user_stopped = True
    if retry_timer:
        retry_timer.cancel()
        retry_timer = None
    with process_lock:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=8)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
    return jsonify({"ok": True, "message": "已暂停"})


@app.route("/api/logs/stream")
def api_logs_stream():
    def generate():
        q = queue.Queue()
        log_queues.append(q)
        try:
            while True:
                try:
                    line = q.get(timeout=30)
                    yield f"data: {json.dumps({'line': line})}\n\n"
                except queue.Empty:
                    yield f"data: {json.dumps({'ping': True})}\n\n"
        finally:
            try:
                log_queues.remove(q)
            except ValueError:
                pass

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main():
    import argparse
    p = argparse.ArgumentParser(description="OKX 交易机器人 Web 控制台")
    p.add_argument("--host", default="127.0.0.1", help="监听地址")
    p.add_argument("--port", type=int, default=5555, help="端口")
    p.add_argument("--debug", action="store_true", help="Flask debug")
    args = p.parse_args()
    print(f"控制台: http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
