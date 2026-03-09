(function () {
  const form = document.getElementById("envForm");
  const msg = document.getElementById("msg");

  function setPlaceholders(status) {
    ["OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"].forEach(function (key) {
      var el = form.elements[key];
      if (el) el.placeholder = status[key] === "set" ? "已配置，留空不修改" : "未配置，请填写";
    });
  }

  fetch("/api/env")
    .then(function (r) { return r.json(); })
    .then(setPlaceholders)
    .catch(function () { msg.textContent = "加载失败"; });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var data = {};
    ["OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"].forEach(function (key) {
      var val = (form.elements[key] && form.elements[key].value) || "";
      data[key] = val.trim();
    });
    msg.textContent = "保存中…";
    fetch("/api/env", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        msg.textContent = "已保存，对新启动的机器人生效。";
        setPlaceholders(d.status || {});
        if (form.elements.OKX_API_KEY) form.elements.OKX_API_KEY.value = "";
        if (form.elements.OKX_API_SECRET) form.elements.OKX_API_SECRET.value = "";
        if (form.elements.OKX_PASSPHRASE) form.elements.OKX_PASSPHRASE.value = "";
      })
      .catch(function () { msg.textContent = "保存失败"; });
  });
})();
