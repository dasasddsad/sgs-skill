"use strict";
/* 三国杀 Agent 前端逻辑 */
(function () {
  const $ = (id) => document.getElementById(id);
  const descEl = $("desc");
  const providerEl = $("provider");
  const runBtn = $("runBtn");
  const copyBtn = $("copyBtn");
  const downloadBtn = $("downloadBtn");
  const errEl = $("err");

  let lastFiles = [];   // [{path,label,content}]
  let curFile = 0;
  let busy = false;

  // ---------- 初始化：加载 provider 与示例 ----------
  fetch("/api/config")
    .then((r) => r.json())
    .then((cfg) => {
      cfg.providers.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.name + (p.configured ? "" : "（未配置）");
        providerEl.appendChild(opt);
      });
      if (cfg.default_provider && cfg.default_provider !== "auto") {
        providerEl.value = cfg.default_provider;
      }
      const box = $("presets");
      cfg.presets.forEach((pr) => {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = pr.name;
        chip.title = pr.description;
        chip.onclick = () => {
          descEl.value = pr.description;
          descEl.focus();
        };
        box.appendChild(chip);
      });
    })
    .catch((e) => showError("加载配置失败：" + e));

  // ---------- 运行 ----------
  runBtn.onclick = async () => {
    const description = descEl.value.trim();
    if (!description) {
      showError("请先输入武将描述。");
      return;
    }
    setBusy(true);
    hideError();
    resetResult();
    try {
      const resp = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description, provider: providerEl.value }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        throw new Error(data.error || ("请求失败（HTTP " + resp.status + "）"));
      }
      render(data);
    } catch (e) {
      showError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  // ---------- 渲染 ----------
  function render(data) {
    $("resultCard").hidden = false;

    // 流水线
    $("stageCard").hidden = false;
    const ol = $("stages");
    ol.innerHTML = "";
    data.stages.forEach((st) => {
      const li = document.createElement("li");
      const b = document.createElement("b");
      b.textContent = st.name;
      li.appendChild(b);
      li.appendChild(document.createTextNode(st.detail));
      ol.appendChild(li);
    });

    $("meta").textContent = `${data.provider} 提供方 · 耗时 ${data.elapsed}s · ${data.saved_files.length} 文件已保存`;
    $("specOut").textContent = JSON.stringify(data.spec, null, 2);
    $("summaryOut").textContent = data.spec_summary;

    const warnUl = $("warnOut");
    warnUl.innerHTML = "";
    const warns = data.warnings || [];
    $("warnCount").textContent = warns.length;
    if (!warns.length) {
      const li = document.createElement("li");
      li.textContent = "✓ 无警告，代码结构已通过括号配平检查。";
      warnUl.appendChild(li);
    } else {
      warns.forEach((w) => {
        const li = document.createElement("li");
        li.textContent = "! " + w;
        warnUl.appendChild(li);
      });
    }

    // 文件选择器
    lastFiles = data.files;
    curFile = 0;
    const sel = $("fileSelect");
    sel.innerHTML = "";
    data.files.forEach((f, i) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = f.path;
      sel.appendChild(opt);
    });
    sel.onchange = () => {
      curFile = parseInt(sel.value, 10) || 0;
      $("fileOut").textContent = lastFiles[curFile].content;
    };
    $("fileOut").textContent = lastFiles[0].content;
    copyBtn.disabled = false;
    downloadBtn.disabled = false;
  }

  function resetResult() {
    $("resultCard").hidden = true;
    $("stageCard").hidden = true;
  }

  // ---------- 工具栏 ----------
  copyBtn.onclick = async () => {
    const f = lastFiles[curFile];
    if (!f) return;
    try {
      await navigator.clipboard.writeText(f.content);
      flash(copyBtn, "✓ 已复制 " + f.label);
    } catch {
      // 降级：选中文本
      const pre = $("fileOut");
      const range = document.createRange();
      range.selectNodeContents(pre);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      flash(copyBtn, "请手动 Ctrl+C");
    }
  };

  downloadBtn.onclick = () => {
    lastFiles.forEach((f) => {
      const blob = new Blob([f.content], { type: "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = f.path.split("/").pop();
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        URL.revokeObjectURL(a.href);
        a.remove();
      }, 200);
    });
    flash(downloadBtn, "✓ 已下载 " + lastFiles.length + " 个文件");
  };

  // ---------- Tab 切换 ----------
  document.querySelectorAll(".tab").forEach((tb) => {
    tb.onclick = () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      tb.classList.add("active");
      $("pane-" + tb.dataset.tab).classList.add("active");
    };
  });

  // ---------- 小工具 ----------
  function showError(msg) {
    errEl.textContent = "✕ " + msg;
    errEl.hidden = false;
  }
  function hideError() {
    errEl.hidden = true;
  }
  function setBusy(v) {
    busy = v;
    runBtn.disabled = v;
    runBtn.textContent = v ? "⏳ 生成中…" : "🚀 生成武将代码";
  }
  let timer = null;
  function flash(btn, text) {
    const old = btn.textContent;
    btn.textContent = text;
    clearTimeout(timer);
    timer = setTimeout(() => (btn.textContent = old), 1600);
  }
})();
