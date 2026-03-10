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
from datetime import datetime
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
sys.path.insert(0, str(ROOT))

# 可在页面配置的环境变量（与 .env 对应）
ENV_KEYS = [
    ("OKX_API_KEY", "OKX API Key"),
    ("OKX_API_SECRET", "OKX API Secret"),
    ("OKX_PASSPHRASE", "OKX Passphrase（创建 API 时自设的密码）"),
]

try:
    from flask import Flask, request, jsonify, Response, send_from_directory
except ImportError:
    print("请安装: pip install flask")
    sys.exit(1)

app = Flask(__name__, static_folder=str(ROOT / "web" / "static"), static_url_path="")

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
    "ratio": 0.35,
    "interval": 60,
    "taker_fee_rate": 0.001,
    "buy_amount_usdt": 50.0,
    "min_buy_usdt": 10.0,
    "max_slippage": 0.001,
    "cooldown_sec": 60,
    "sell_fee_compensation_pct": 0.15,
    "empty_rebase_up_pct": 1.0,
    "exec_quality_threshold_pct": 0.1,
    "exec_pause_sec": 300,
}


def params_to_argv(params: dict) -> list:
    """将参数字典转为 run_okx_live.py 命令行参数."""
    cmd = [sys.executable, str(ROOT / "run_okx_live.py")]
    cmd += ["--symbol", str(params.get("symbol", "BTC/USDT"))]
    cmd += ["--ratio", str(params.get("ratio", 0.5))]
    cmd += ["--interval", str(params.get("interval", 60))]
    cmd += ["--taker-fee-rate", str(params.get("taker_fee_rate", 0.001))]
    cmd += ["--buy-amount-usdt", str(params.get("buy_amount_usdt", 50))]
    cmd += ["--min-buy-usdt", str(params.get("min_buy_usdt", 10))]
    cmd += ["--max-slippage", str(params.get("max_slippage", 0.001))]
    cmd += ["--cooldown-sec", str(params.get("cooldown_sec", 60))]
    cmd += ["--sell-fee-compensation-pct", str(params.get("sell_fee_compensation_pct", 0.2))]
    cmd += ["--empty-rebase-up-pct", str(params.get("empty_rebase_up_pct", 1.0))]
    cmd += ["--exec-quality-threshold-pct", str(params.get("exec_quality_threshold_pct", 0.1))]
    cmd += ["--exec-pause-sec", str(params.get("exec_pause_sec", 300))]
    return cmd


def broadcast_log(line: str):
    for q in list(log_queues):
        try:
            q.put_nowait(line)
        except Exception:
            pass


def system_log(message: str):
    broadcast_log(f"[{datetime.now().strftime('%H:%M:%S')}] [系统] {message}\n")


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
    system_log(f"已启动: {' '.join(argv)}")
    try:
        for line in iter(process.stdout.readline, ""):
            broadcast_log(line)
    except Exception as e:
        system_log(f"读取输出异常: {e}")
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
        system_log(f"进程已退出，code={code}")
        if user_stopped:
            user_stopped = False
            return
        if code != 0 and retry_count < max_auto_retries:
            retry_count += 1
            system_log(f"{retry_delay_sec} 秒后进行第 {retry_count}/{max_auto_retries} 次自动重试…")
            def retry_later():
                global retry_timer
                retry_timer = None
                run_bot_worker(params)
            retry_timer = threading.Timer(retry_delay_sec, retry_later)
            retry_timer.start()
        else:
            if retry_count >= max_auto_retries:
                system_log(f"已达最大自动重试次数 ({max_auto_retries})，停止重试。")
            retry_count = 0


current_params: dict = dict(DEFAULT_PARAMS)


def _read_env_status() -> dict:
    """返回各 key 是否已配置（set/unset），不返回具体值。"""
    status = {key: "unset" for key, _ in ENV_KEYS}
    if not ENV_FILE.exists():
        return status
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = (v.strip().strip('"').strip("'") or "").strip()
                if k in status and v:
                    status[k] = "set"
    except Exception:
        pass
    return status


def _write_env_updates(updates: dict):
    """只更新给定 key，其余行与注释尽量保留。"""
    lines = []
    if ENV_FILE.exists():
        try:
            text = ENV_FILE.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, _ = line.partition("=")
                    key = k.strip()
                    if key in updates:
                        lines.append(f"{key}={updates[key]}")
                        del updates[key]
                        continue
                lines.append(line)
        except Exception:
            lines = []
    for k, v in updates.items():
        lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/config")
def config_page():
    return send_from_directory(app.static_folder, "config.html")


@app.route("/api/env", methods=["GET"])
def api_get_env():
    """返回各 key 是否已配置（set/unset），不返回明文。"""
    return jsonify(_read_env_status())


@app.route("/api/env", methods=["POST"])
def api_set_env():
    """更新 .env 中指定 key，请求体为 { key: value }。值为空则不修改该键。"""
    data = request.get_json() or {}
    updates = {}
    for key, _ in ENV_KEYS:
        if key in data and data[key] is not None:
            v = str(data[key]).strip()
            if v:
                updates[key] = v
    if updates:
        _write_env_updates(updates)
        # 当前进程环境不会自动更新，仅对新启动的机器人生效
    return jsonify({"ok": True, "status": _read_env_status()})


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
            if k in ("symbol",):
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
                if k == "symbol":
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
