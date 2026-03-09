(function () {
  const statusPill = document.getElementById("statusPill");
  const btnStart = document.getElementById("btnStart");
  const btnStop = document.getElementById("btnStop");
  const retryHint = document.getElementById("retryHint");
  const paramsForm = document.getElementById("paramsForm");
  const logEl = document.getElementById("log");

  function setRunning(running) {
    statusPill.textContent = running ? "运行中" : "已停止";
    statusPill.classList.toggle("running", running);
    btnStart.disabled = running;
    btnStop.disabled = !running;
  }

  function getFormParams() {
    const fd = new FormData(paramsForm);
    return {
      symbol: (fd.get("symbol") || "BTC/USDT").trim(),
      ratio: parseFloat(fd.get("ratio")) || 0.35,
      sell_fee_compensation_pct: parseFloat(fd.get("sell_fee_compensation_pct")) || 0.15,
      interval: parseFloat(fd.get("interval")) || 60,
      cooldown_sec: parseFloat(fd.get("cooldown_sec")) || 60,
      buy_amount_usdt: parseFloat(fd.get("buy_amount_usdt")) || 50,
      min_buy_usdt: parseFloat(fd.get("min_buy_usdt")) || 10,
      taker_fee_rate: parseFloat(fd.get("taker_fee_rate")) || 0.001,
      max_slippage: parseFloat(fd.get("max_slippage")) || 0.001,
      exec_quality_threshold_pct: parseFloat(fd.get("exec_quality_threshold_pct")) || 0.1,
      exec_pause_sec: parseFloat(fd.get("exec_pause_sec")) || 300,
    };
  }

  function setFormParams(p) {
    if (!p) return;
    const set = (name, value) => {
      const el = paramsForm.elements[name];
      if (el) el.value = value;
    };
    const setCheck = (name, value) => {
      const el = paramsForm.elements[name];
      if (el) el.checked = !!value;
    };
    set("symbol", p.symbol);
    set("ratio", p.ratio);
    set("sell_fee_compensation_pct", p.sell_fee_compensation_pct);
    set("interval", p.interval);
    set("cooldown_sec", p.cooldown_sec);
    set("buy_amount_usdt", p.buy_amount_usdt);
    set("min_buy_usdt", p.min_buy_usdt);
    set("taker_fee_rate", p.taker_fee_rate);
    set("max_slippage", p.max_slippage);
    set("exec_quality_threshold_pct", p.exec_quality_threshold_pct);
    set("exec_pause_sec", p.exec_pause_sec);
  }

  async function fetchStatus() {
    const r = await fetch("/api/status");
    const d = await r.json();
    setRunning(d.running);
    setFormParams(d.params);
    if (d.retry_count > 0) {
      retryHint.textContent = `自动重试: ${d.retry_count} / ${d.max_auto_retries}`;
    } else {
      retryHint.textContent = "";
    }
    return d;
  }

  function appendLog(line) {
    logEl.appendChild(document.createTextNode(line));
    logEl.scrollTop = logEl.scrollHeight;
  }

  function appendSystemLog(message) {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    appendLog(`[${time}] [系统] ${message}\n`);
  }

  function connectLogStream() {
    const es = new EventSource("/api/logs/stream");
    es.onmessage = function (e) {
      try {
        const d = JSON.parse(e.data);
        if (d.line) appendLog(d.line);
      } catch (_) {}
    };
    es.onerror = function () {
      es.close();
      setTimeout(connectLogStream, 2000);
    };
  }

  btnStart.addEventListener("click", async () => {
    const params = getFormParams();
    const r = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    const d = await r.json();
    if (d.ok) {
      setRunning(true);
      appendSystemLog("启动请求已发送");
    } else {
      appendSystemLog(d.message || "启动失败");
    }
  });

  btnStop.addEventListener("click", async () => {
    const r = await fetch("/api/stop", { method: "POST" });
    const d = await r.json();
    if (d.ok) {
      setRunning(false);
      appendSystemLog("已发送暂停请求");
    }
  });

  setInterval(fetchStatus, 2000);
  fetchStatus();
  connectLogStream();
})();
