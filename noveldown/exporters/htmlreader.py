#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单文件 HTML 阅读器导出：零第三方依赖，双击即读，可直接放手机。

特性
----
- 目录侧栏：搜索过滤 + 点击跳转
- 阅读导航：上一章 / 下一章 + 键盘（← → / j k / 空格）
- 阅读进度：localStorage 记住当前章与滚动位置，重开续读
- 阅读设置：字号缩放 / 三档主题（日间 / 米黄 / 夜间）/ 行距
- 章节内容以 JSON 内嵌，按需渲染（避免上千章时 DOM 爆炸）
"""

import html as html_mod
import json
import os

from ..freeguard import assert_no_protected, filter_exportable
from . import book_slug, ensure_dir, register


def _esc_json_in_html(s: str) -> str:
    """避免内嵌 JSON 里的 </script> 提前闭合脚本标签。"""
    return (s.replace("<", "\\u003c")
             .replace(">", "\\u003e")
             .replace("&", "\\u0026"))


@register("html")
def export(book, out_dir: str) -> str:
    assert_no_protected(book.chapters, context="html 阅读器导出")
    ensure_dir(out_dir)
    path = os.path.join(out_dir, f"{book_slug(book)}.html")

    chapters = filter_exportable(book.chapters)
    data = {
        "title": book.title,
        "author": book.author,
        "site": book.site,
        "source": book.url,
        "intro": book.intro,
        "chapters": [
            {"i": c.index, "t": c.title, "v": c.volume, "p": c.paragraphs}
            for c in chapters
        ],
    }
    payload = _esc_json_in_html(json.dumps(data, ensure_ascii=False))

    html = _TEMPLATE.replace("__BOOK_TITLE__", html_mod.escape(book.title or "未命名"))
    html = html.replace("__BOOK_JSON__", payload)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    return path


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__BOOK_TITLE__ · 离线阅读器</title>
<style>
  :root{
    --bg:#ffffff; --fg:#1f2328; --muted:#6b7280; --line:#e5e7eb;
    --panel:#fafafa; --accent:#b45309; --shadow:0 1px 3px rgba(0,0,0,.08);
  }
  html[data-theme="sepia"]{ --bg:#f5efe1; --fg:#3b3226; --muted:#8a7c66;
    --line:#e2d7c0; --panel:#efe7d5; --accent:#8a5a1e; }
  html[data-theme="dark"]{ --bg:#16181d; --fg:#d7dae0; --muted:#8b93a1;
    --line:#2a2e37; --panel:#1d2027; --accent:#e0a45c;
    --shadow:0 1px 3px rgba(0,0,0,.5); }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0;background:var(--bg);color:var(--fg)}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",
       "PingFang SC","Hiragino Sans GB",sans-serif;
       font-size:var(--fs,17px); line-height:var(--lh,1.85);}
  #app{display:flex;min-height:100vh}

  /* ---------- 侧栏 ---------- */
  #side{width:300px;flex:0 0 300px;background:var(--panel);
        border-right:1px solid var(--line);height:100vh;position:sticky;top:0;
        display:flex;flex-direction:column;transition:margin-left .22s ease}
  #side.hide{margin-left:-300px}
  .side-head{padding:14px 14px 10px;border-bottom:1px solid var(--line)}
  .side-head h1{font-size:15px;margin:0 0 2px;font-weight:600;line-height:1.4}
  .side-head .au{font-size:12px;color:var(--muted);margin-bottom:9px}
  .side-head input{width:100%;padding:7px 9px;font-size:13px;border:1px solid var(--line);
    border-radius:7px;background:var(--bg);color:var(--fg);outline:none}
  .side-head input:focus{border-color:var(--accent)}
  #toc{flex:1;overflow-y:auto;padding:6px 0 60px}
  #toc a{display:block;padding:6px 14px;font-size:13.5px;color:var(--fg);
    text-decoration:none;border-left:2px solid transparent;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #toc a:hover{background:rgba(127,127,127,.10)}
  #toc a.cur{border-left-color:var(--accent);color:var(--accent);font-weight:600;
    background:rgba(127,127,127,.08)}
  #toc a .n{color:var(--muted);font-size:11.5px;margin-right:7px;font-variant-numeric:tabular-nums}
  #toc .vol{padding:12px 14px 5px;font-size:11.5px;letter-spacing:.06em;
    color:var(--muted);text-transform:uppercase}

  /* ---------- 正文 ---------- */
  #main{flex:1;min-width:0;display:flex;flex-direction:column}
  #bar{position:sticky;top:0;z-index:5;background:var(--bg);
       border-bottom:1px solid var(--line);display:flex;align-items:center;
       gap:8px;padding:8px 14px;backdrop-filter:blur(6px)}
  #bar .sp{flex:1}
  .btn{border:1px solid var(--line);background:var(--panel);color:var(--fg);
    font-size:12.5px;padding:5px 10px;border-radius:7px;cursor:pointer;
    white-space:nowrap}
  .btn:hover{border-color:var(--accent);color:var(--accent)}
  #pos{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
  #prog{height:2px;background:transparent}
  #prog i{display:block;height:2px;width:0;background:var(--accent);transition:width .18s}

  article{max-width:44em;margin:0 auto;padding:38px 26px 120px;width:100%}
  article h1{font-size:1.34em;line-height:1.5;margin:0 0 6px;font-weight:600}
  .voltag{font-size:12.5px;color:var(--muted);margin:0 0 22px;
    padding-bottom:12px;border-bottom:1px solid var(--line)}
  article p{margin:0 0 .72em;text-indent:2em;word-wrap:break-word}
  #empty{color:var(--muted);text-align:center;padding:80px 20px;text-indent:0}
  .nav{display:flex;gap:10px;margin-top:44px;padding-top:20px;
       border-top:1px solid var(--line)}
  .nav button{flex:1;padding:11px;border:1px solid var(--line);border-radius:9px;
    background:var(--panel);color:var(--fg);cursor:pointer;font-size:14px}
  .nav button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
  .nav button:disabled{opacity:.4;cursor:default}

  /* ---------- 设置面板 ---------- */
  #cfg{position:fixed;right:16px;bottom:16px;z-index:20;background:var(--panel);
    border:1px solid var(--line);border-radius:12px;padding:12px 14px;
    box-shadow:var(--shadow);display:none;min-width:212px}
  #cfg.on{display:block}
  #cfg h4{margin:0 0 9px;font-size:12.5px;color:var(--muted);font-weight:600}
  #cfg .row{display:flex;align-items:center;gap:8px;margin-bottom:9px;font-size:12.5px}
  #cfg .row span{color:var(--muted);flex:0 0 34px}
  #cfg input[type=range]{flex:1}
  #cfg .themes{display:flex;gap:6px}
  #cfg .themes button{flex:1;padding:6px 4px;font-size:12px;border-radius:7px;
    border:1px solid var(--line);background:var(--bg);color:var(--fg);cursor:pointer}
  #cfg .themes button.on{border-color:var(--accent);color:var(--accent);font-weight:600}

  /* 移动端：目录变抽屉 + 遮罩 */
  #mask{display:none;position:fixed;inset:0;background:rgba(0,0,0,.42);z-index:14}
  #mask.on{display:block}

  @media (max-width:820px){
    #side{position:fixed;z-index:15;box-shadow:var(--shadow)}
    #side.hide{margin-left:-300px}
    article{padding:24px 18px 110px}
  }
</style>
</head>
<body>
<div id="app">
  <aside id="side">
    <div class="side-head">
      <h1 id="bk-title"></h1>
      <div class="au" id="bk-author"></div>
      <input id="q" type="search" placeholder="搜索章节…" autocomplete="off">
    </div>
    <nav id="toc"></nav>
  </aside>
  <div id="mask"></div>

  <div id="main">
    <div id="bar">
      <button class="btn" id="toggle" title="显示/隐藏目录">☰</button>
      <span id="pos">– / –</span>
      <span class="sp"></span>
      <button class="btn" id="prevTop">上一章</button>
      <button class="btn" id="nextTop">下一章</button>
      <button class="btn" id="cfgBtn" title="阅读设置">Aa</button>
    </div>
    <div id="prog"><i></i></div>
    <article id="art"><div id="empty">正在载入…</div></article>
  </div>
</div>

<div id="cfg">
  <h4>阅读设置</h4>
  <div class="row"><span>字号</span><input type="range" id="fs" min="14" max="26" step="1"></div>
  <div class="row"><span>行距</span><input type="range" id="lh" min="15" max="26" step="1"></div>
  <div class="row" style="display:block">
    <div class="themes">
      <button data-t="light">日间</button>
      <button data-t="sepia">米黄</button>
      <button data-t="dark">夜间</button>
    </div>
  </div>
</div>

<script id="book" type="application/json">__BOOK_JSON__</script>
<script>
(function(){
  "use strict";
  var BOOK = JSON.parse(document.getElementById("book").textContent);
  var CH = BOOK.chapters || [];
  var KEY = "noveldown:" + (BOOK.source || BOOK.title || "book");

  var art = document.getElementById("art");
  var toc = document.getElementById("toc");
  var posEl = document.getElementById("pos");
  var progEl = document.querySelector("#prog i");
  var cur = 0;

  document.getElementById("bk-title").textContent = BOOK.title || "未命名";
  document.getElementById("bk-author").textContent =
    (BOOK.author ? "作者：" + BOOK.author : "") + (BOOK.site ? "　·　" + BOOK.site : "");
  document.title = (BOOK.title || "阅读器") + " · 离线阅读器";

  /* ---------- 目录 ---------- */
  var vol = null;
  CH.forEach(function(c, idx){
    if (c.v && c.v !== vol){
      vol = c.v;
      var d = document.createElement("div");
      d.className = "vol"; d.textContent = vol;
      d.dataset.vol = "1";
      toc.appendChild(d);
    }
    var a = document.createElement("a");
    a.href = "#" + idx; a.dataset.i = idx;
    a.innerHTML = '<span class="n">' + (idx + 1) + '</span>';
    a.appendChild(document.createTextNode(c.t || ("第" + (idx+1) + "章")));
    a.onclick = function(e){
      e.preventDefault(); go(idx);
      if (isNarrow()) toggleSide(false);   // 移动端选完章节自动收起抽屉
    };
    toc.appendChild(a);
  });
  var tocLinks = Array.prototype.slice.call(toc.querySelectorAll("a[data-i]"));
  var tocVols  = Array.prototype.slice.call(toc.querySelectorAll("div.vol"));

  /* ---------- 搜索 ---------- */
  document.getElementById("q").addEventListener("input", function(e){
    var q = e.target.value.trim().toLowerCase();
    tocLinks.forEach(function(a){
      var t = (CH[+a.dataset.i].t || "").toLowerCase();
      a.style.display = (!q || t.indexOf(q) >= 0) ? "" : "none";
    });
    tocVols.forEach(function(d){ d.style.display = q ? "none" : ""; });
  });

  /* ---------- 渲染 ---------- */
  function esc(s){
    return String(s).replace(/[&<>]/g, function(m){
      return m === "&" ? "&amp;" : m === "<" ? "&lt;" : "&gt;";
    });
  }
  function go(i, keepScroll){
    if (i < 0 || i >= CH.length) return;
    cur = i;
    var c = CH[i];
    var h = [];
    if (c.v) h.push('<div class="voltag">' + esc(c.v) + '</div>');
    h.push('<h1>' + esc(c.t || ("第" + (i+1) + "章")) + '</h1>');
    (c.p || []).forEach(function(p){ h.push('<p>' + esc(p) + '</p>'); });
    h.push('<div class="nav">' +
      '<button id="pv"' + (i === 0 ? " disabled" : "") + '>← 上一章</button>' +
      '<button id="nx"' + (i === CH.length-1 ? " disabled" : "") + '>下一章 →</button>' +
      '</div>');
    art.innerHTML = h.join("");
    var pv = document.getElementById("pv"), nx = document.getElementById("nx");
    if (pv) pv.onclick = function(){ go(cur-1); };
    if (nx) nx.onclick = function(){ go(cur+1); };

    tocLinks.forEach(function(a){ a.classList.toggle("cur", +a.dataset.i === i); });
    var act = tocLinks[i];
    if (act && act.scrollIntoView) act.scrollIntoView({block:"nearest"});
    posEl.textContent = (i+1) + " / " + CH.length;
    progEl.style.width = ((i+1) / CH.length * 100).toFixed(2) + "%";
    document.getElementById("prevTop").disabled = (i === 0);
    document.getElementById("nextTop").disabled = (i === CH.length-1);
    if (!keepScroll) window.scrollTo(0, 0);
    save();
  }

  /* ---------- 进度记忆 ---------- */
  var saveTimer = null;
  function save(){
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function(){
      try{
        localStorage.setItem(KEY, JSON.stringify({i: cur, y: window.scrollY}));
      }catch(e){}
    }, 180);
  }
  function load(){
    try{
      var s = JSON.parse(localStorage.getItem(KEY) || "null");
      if (s && typeof s.i === "number") return s;
    }catch(e){}
    return null;
  }
  window.addEventListener("scroll", save, {passive:true});

  /* ---------- 键盘 ---------- */
  document.addEventListener("keydown", function(e){
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
    if (e.key === "ArrowLeft" || e.key === "k") { go(cur-1); }
    else if (e.key === "ArrowRight" || e.key === "j" || e.key === " ") {
      e.preventDefault(); go(cur+1);
    }
    else if (e.key === "Home") { go(0); }
    else if (e.key === "End") { go(CH.length-1); }
  });

  document.getElementById("prevTop").onclick = function(){ go(cur-1); };
  document.getElementById("nextTop").onclick = function(){ go(cur+1); };

  /* ---------- 侧栏开合（移动端为抽屉 + 遮罩）---------- */
  var side = document.getElementById("side");
  var mask = document.getElementById("mask");
  function isNarrow(){ return window.matchMedia("(max-width:820px)").matches; }
  function syncMask(){
    var open = !side.classList.contains("hide");
    mask.classList.toggle("on", open && isNarrow());
  }
  function toggleSide(force){
    var willOpen = (force === undefined) ? side.classList.contains("hide") : force;
    side.classList.toggle("hide", !willOpen);
    syncMask();
  }
  document.getElementById("toggle").onclick = function(){ toggleSide(); };
  mask.onclick = function(){ toggleSide(false); };

  // 由「宽」变「窄」时自动收起抽屉——否则侧栏会盖住顶部工具条上的 ☰ 按钮，
  // 用户反而点不到开合按钮（Playwright 实测踩到：pointer events intercepted）。
  var wasNarrow = isNarrow();
  window.addEventListener("resize", function(){
    var nowNarrow = isNarrow();
    if (nowNarrow && !wasNarrow) toggleSide(false);
    wasNarrow = nowNarrow;
    syncMask();
  });
  document.addEventListener("keydown", function(e){
    if (e.key === "Escape" && isNarrow()) toggleSide(false);
  });

  /* ---------- 设置 ---------- */
  var root = document.documentElement;
  var st = {fs: 17, lh: 18, theme: "light"};
  try{ Object.assign(st, JSON.parse(localStorage.getItem(KEY + ":cfg") || "{}")); }catch(e){}

  function applyCfg(){
    root.style.setProperty("--fs", st.fs + "px");
    root.style.setProperty("--lh", (st.lh / 10).toFixed(2));
    root.setAttribute("data-theme", st.theme);
    document.getElementById("fs").value = st.fs;
    document.getElementById("lh").value = st.lh;
    Array.prototype.forEach.call(document.querySelectorAll("#cfg .themes button"),
      function(b){ b.classList.toggle("on", b.dataset.t === st.theme); });
    try{ localStorage.setItem(KEY + ":cfg", JSON.stringify(st)); }catch(e){}
  }
  document.getElementById("fs").oninput = function(e){ st.fs = +e.target.value; applyCfg(); };
  document.getElementById("lh").oninput = function(e){ st.lh = +e.target.value; applyCfg(); };
  Array.prototype.forEach.call(document.querySelectorAll("#cfg .themes button"),
    function(b){ b.onclick = function(){ st.theme = b.dataset.t; applyCfg(); }; });
  document.getElementById("cfgBtn").onclick = function(){
    document.getElementById("cfg").classList.toggle("on");
  };

  /* ---------- 启动 ---------- */
  applyCfg();
  if (isNarrow()) toggleSide(false);   // 窄屏默认收起抽屉
  if (!CH.length){
    art.innerHTML = '<div id="empty">本书没有可导出的章节（可能全部被免费章节策略拦截）。</div>';
    posEl.textContent = "0 / 0";
    return;
  }
  var s = load();
  go(s ? Math.min(s.i, CH.length-1) : 0, true);
  if (s && s.y) window.scrollTo(0, s.y);
})();
</script>
</body>
</html>
"""
