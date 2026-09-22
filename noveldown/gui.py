#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""novel-down 的 Tkinter 图形界面。

设计原则：**只做外壳，不复制核心逻辑**。
抓取仍走 `engine.Downloader`，导出仍走 `exporters.export_all`，
校对仍走 `proofread` —— GUI 只是把 CLI 的流程接到控件上、把日志接到文本框。

⚠ 为什么用 Tkinter：**零第三方依赖**（标准库），且本机 `<你的 Python 环境>` 自带 Tcl/Tk 9，
可直接被 PyInstaller 打进 exe（见 packaging/README.md）。

线程模型：
    UI 线程只做界面；抓取跑在**后台线程**里（否则界面全程卡死）。
    后台线程**不能**碰 Tk 控件 —— 所有日志/进度都塞进 `queue.Queue`，
    由 UI 线程用 `after()` 定时取出刷新。

启动：
    python -m noveldown.gui
    noveldown-gui            （打包后的 exe 名，见 packaging/entry_gui.py）
"""

import os
import queue
import sys
import threading
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .cli import APP_TITLE, _config_from_args  # noqa: F401  (复用 config 构造)
from .constants import DEFAULT_CONFIG, VERSION
from .rules import RuleError, load_rules

# 允许导出的格式（与 exporters 注册的一致）
FORMATS = [("txt", "纯文本 TXT"), ("md", "Markdown"), ("epub", "EPUB 电子书"),
           ("html", "单文件 HTML 阅读器")]

LEVEL_ICON = {"info": "·", "ok": "✓", "warn": "⚠", "error": "✗"}


class _Args:
    """把 GUI 控件上的值伪装成 CLI 的 argparse 结果，好复用 `_config_from_args`。"""

    def __init__(self, url, out, concurrency, delay, timeout, retries, proxy,
                 curl_cffi=False, formats="txt,md,epub,html", quiet=False):
        self.url = url
        self.out = out
        self.concurrency = concurrency
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.proxy = proxy
        self.curl_cffi = curl_cffi
        self.formats = formats
        self.quiet = quiet
        self.limit = 0
        self.force = False
        self.max_items = 20
        self.report = False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"novel-down {VERSION} — 规则驱动的免费章节下载器")
        self.geometry("900x680")
        self.minsize(760, 560)

        self._q = queue.Queue()          # 后台线程 → UI 线程的消息
        self._worker = None
        self._stop_flag = threading.Event()
        self._rules = {}

        self._build_ui()
        self._load_rules()
        self.after(120, self._drain_queue)

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- 站点 ---
        f1 = ttk.LabelFrame(self, text="1. 选择站点")
        f1.pack(fill="x", **pad)
        row = ttk.Frame(f1)
        row.pack(fill="x", padx=8, pady=6)
        ttk.Label(row, text="搜索：").pack(side="left")
        self.var_search = tk.StringVar()
        e = ttk.Entry(row, textvariable=self.var_search, width=26)
        e.pack(side="left", padx=(0, 8))
        e.bind("<KeyRelease>", lambda _e: self._refresh_sites())
        ttk.Label(row, text="站点：").pack(side="left")
        self.cmb_site = ttk.Combobox(row, width=58, state="readonly")
        self.cmb_site.pack(side="left", fill="x", expand=True)
        self.cmb_site.bind("<<ComboboxSelected>>", self._on_site_pick)
        ttk.Label(f1, text="（“正版”= 官方站点的免费章节；“免费镜像”= 由深扫逐站实测通过的镜像域名）",
                  foreground="#666").pack(anchor="w", padx=10, pady=(0, 6))

        # --- URL 与参数 ---
        f2 = ttk.LabelFrame(self, text="2. 书籍地址与参数")
        f2.pack(fill="x", **pad)
        r2 = ttk.Frame(f2)
        r2.pack(fill="x", padx=8, pady=6)
        ttk.Label(r2, text="书籍 URL：").pack(side="left")
        self.var_url = tk.StringVar()
        ttk.Entry(r2, textvariable=self.var_url).pack(side="left", fill="x", expand=True)

        r3 = ttk.Frame(f2)
        r3.pack(fill="x", padx=8, pady=(0, 8))
        self.var_conc = tk.IntVar(value=int(DEFAULT_CONFIG.get("concurrency", 4)))
        self.var_delay = tk.DoubleVar(value=float(DEFAULT_CONFIG.get("delay", 1.2)))
        self.var_limit = tk.IntVar(value=0)
        self.var_force = tk.BooleanVar(value=False)
        ttk.Label(r3, text="并发").pack(side="left")
        ttk.Spinbox(r3, from_=1, to=16, width=4, textvariable=self.var_conc).pack(side="left", padx=(2, 10))
        ttk.Label(r3, text="间隔(秒)").pack(side="left")
        ttk.Spinbox(r3, from_=0, to=10, increment=0.2, width=5,
                    textvariable=self.var_delay).pack(side="left", padx=(2, 10))
        ttk.Label(r3, text="只抓前 N 章(0=全部)").pack(side="left")
        ttk.Spinbox(r3, from_=0, to=99999, width=7, textvariable=self.var_limit).pack(side="left", padx=(2, 10))
        ttk.Checkbutton(r3, text="忽略断点重抓", variable=self.var_force).pack(side="left")

        r4 = ttk.Frame(f2)
        r4.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(r4, text="导出格式：").pack(side="left")
        self.var_fmt = {}
        for key, label in FORMATS:
            v = tk.BooleanVar(value=True)
            self.var_fmt[key] = v
            ttk.Checkbutton(r4, text=label, variable=v).pack(side="left", padx=(0, 10))
        ttk.Label(r4, text="  输出目录：").pack(side="left")
        self.var_out = tk.StringVar(value=os.path.abspath(DEFAULT_CONFIG.get("save_dir", "output")))
        ttk.Entry(r4, textvariable=self.var_out, width=22).pack(side="left")
        ttk.Button(r4, text="…", width=3,
                   command=self._pick_out).pack(side="left", padx=(2, 0))

        # --- 操作 ---
        f3 = ttk.Frame(self)
        f3.pack(fill="x", **pad)
        self.btn_fetch = ttk.Button(f3, text="开始抓取", command=self._start_fetch)
        self.btn_fetch.pack(side="left", padx=(0, 6))
        self.btn_export = ttk.Button(f3, text="仅重新导出", command=self._start_export)
        self.btn_export.pack(side="left", padx=(0, 6))
        self.btn_stop = ttk.Button(f3, text="停止", command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 6))
        ttk.Button(f3, text="打开输出目录", command=self._open_out).pack(side="left")

        # --- 进度 + 日志 ---
        f4 = ttk.LabelFrame(self, text="进度")
        f4.pack(fill="both", expand=True, **pad)
        self.var_prog = tk.DoubleVar(value=0.0)
        self.pb = ttk.Progressbar(f4, variable=self.var_prog, maximum=100)
        self.pb.pack(fill="x", padx=8, pady=(8, 2))
        self.var_stat = tk.StringVar(value="就绪")
        ttk.Label(f4, textvariable=self.var_stat, foreground="#333").pack(anchor="w", padx=10)

        wrap = ttk.Frame(f4)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt = tk.Text(wrap, height=14, wrap="word", state="disabled",
                           background="#fbfbfb", foreground="#111")
        sb = ttk.Scrollbar(wrap, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)

    # ------------------------------------------------------------- 站点表
    def _load_rules(self):
        try:
            self._rules = load_rules()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("规则加载失败", str(e))
            self._rules = {}
        self._refresh_sites()

    def _site_label(self, r):
        pool = {"正版": "正版", "免费镜像": "镜像"}.get(r.pool, r.pool or "?")
        flag = "" if r.enabled else "（停用）"
        return f"[{pool}] {r.id} — {r.name}{flag}"

    def _refresh_sites(self):
        kw = self.var_search.get().strip().lower()
        items = []
        for r in self._rules.values():
            if not r.enabled:
                continue
            hay = f"{r.id} {r.name} {r.pool}".lower()
            if kw and kw not in hay:
                continue
            items.append(self._site_label(r))
        items.sort()
        self.cmb_site["values"] = items
        if items and not self.cmb_site.get():
            self.cmb_site.current(0)

    def _on_site_pick(self, _e=None):
        """选中站点后，把它的 demo_url 填进 URL 框，省得用户去翻 README。"""
        label = self.cmb_site.get()
        rid = label.split("] ", 1)[-1].split(" — ")[0].strip()
        r = self._rules.get(rid)
        if r is not None and getattr(r, "demo_url", ""):
            self._log(f"站点 {rid} 的示例地址已填入（可直接改）", "info")
            self.var_url.set(r.demo_url)

    # ------------------------------------------------------------- 工具
    def _pick_out(self):
        d = filedialog.askdirectory(initialdir=self.var_out.get() or os.getcwd())
        if d:
            self.var_out.set(d)

    def _open_out(self):
        d = self.var_out.get()
        if not os.path.isdir(d):
            messagebox.showinfo("提示", f"目录还不存在：{d}")
            return
        try:
            os.startfile(d)  # noqa: S606  (Windows)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("打开失败", str(e))

    def _log(self, msg, level="info"):
        """线程安全：任何线程都能调，只往队列里塞。"""
        self._q.put(("log", f" {LEVEL_ICON.get(level, '·')} {msg}"))

    def _drain_queue(self):
        """UI 线程定时把队列里的消息刷到控件上（Tk 只能主线程碰）。"""
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "log":
                    self.txt.configure(state="normal")
                    self.txt.insert("end", payload + "\n")
                    self.txt.see("end")
                    self.txt.configure(state="disabled")
                elif kind == "prog":
                    done, total, msg = payload
                    self.var_prog.set(100.0 * done / total if total else 0)
                    self.var_stat.set(f"{done}/{total} {msg}")
                elif kind == "done":
                    self._set_running(False)
                    self.var_stat.set(payload)
                    self._log(payload, "ok")
                elif kind == "fail":
                    self._set_running(False)
                    self.var_stat.set("失败")
                    self._log(payload, "error")
                    messagebox.showerror("出错", payload)
        except queue.Empty:
            pass
        self.after(120, self._drain_queue)

    def _set_running(self, running):
        st = "disabled" if running else "normal"
        self.btn_fetch.configure(state=st)
        self.btn_export.configure(state=st)
        self.btn_stop.configure(state="normal" if running else "disabled")

    def _formats(self):
        """给 `_Args` 用的**字符串**形式（逗号分隔）。"""
        return ",".join(k for k, v in self.var_fmt.items() if v.get())

    def _fmt_list(self):
        """给导出用的 **list** 形式。

        ⚠⚠ 这里曾经写成 `cfg.get("formats", "txt").split(",")` —— 直接崩：
        `DEFAULT_CONFIG["formats"]` 是 **list**（constants.py:113），对 list 调 `.split()`
        必然 `AttributeError: 'list' object has no attribute 'split'`
        （2026-09-22 全哥用 GUI 便携版实测撞到）。
        而且 `_config_from_args()` **根本不处理 formats**，所以 `_Args.formats` 也没生效 ——
        正确的是像 cli._finish 那样，从 args 取**字符串**再切。
        """
        return [k for k, v in self.var_fmt.items() if v.get()]

    # ------------------------------------------------------------- 抓取
    def _start_fetch(self, force=False):
        url = self.var_url.get().strip()
        if not url:
            messagebox.showwarning("缺少地址", "请先填入书籍 URL（选中站点会自动带出示例地址）。")
            return
        fmts = self._fmt_list()
        if not fmts:
            messagebox.showwarning("未选格式", "至少勾选一种导出格式。")
            return
        # ⚠ 格式必须**在 UI 线程里取好**再传进工作线程：Tk 变量不能跨线程读。
        self._run_in_thread(self._do_fetch, url, fmts)

    def _start_export(self):
        url = self.var_url.get().strip()
        if not url:
            messagebox.showwarning("缺少地址", "请先填入书籍 URL。")
            return
        fmts = self._fmt_list()
        if not fmts:
            messagebox.showwarning("未选格式", "至少勾选一种导出格式。")
            return
        self._run_in_thread(self._do_export, url, fmts)

    def _run_in_thread(self, fn, *a):
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("正在运行", "上一个任务还没结束，请先等它完成或点“停止”。")
            return
        self._stop_flag.clear()
        self._set_running(True)
        self.var_prog.set(0)
        self._worker = threading.Thread(target=fn, args=a, daemon=True)
        self._worker.start()

    def _stop(self):
        """请求停止。

        ⚠ 文案要**说清是协作式取消**：不是「立刻断」，也不是「等全部跑完」——
        而是「不再开始新章节，已在跑的那几章会正常收尾并落盘」。
        原来的文案（「会在当前章节结束后停下」）与实际行为（全部跑完）不符，属误导。
        """
        self._stop_flag.set()
        self._log("已请求停止：不会再开始新章节；正在跑的少数几章会正常收尾并落盘"
                  "（断点已保存，重新点“开始抓取”即可续爬）。", "warn")
        self.btn_stop.configure(state="disabled")

    def _args(self, url):
        return _Args(url=url, out=self.var_out.get(),
                     concurrency=self.var_conc.get(), delay=self.var_delay.get(),
                     timeout=float(DEFAULT_CONFIG.get("timeout", 30)),
                     retries=int(DEFAULT_CONFIG.get("retries", 3)),
                     proxy=DEFAULT_CONFIG.get("proxy") or "",
                     formats=self._formats())

    def _do_fetch(self, url, fmts):
        try:
            from .engine import Downloader
            cfg = _config_from_args(self._args(url))
            d = Downloader(url, config=cfg, rules=self._rules,
                           log=self._log, progress=self._prog)
            self._tail_log(f"目标：{url}")
            book = d.run(limit=self.var_limit.get(),
                         force=self.var_force.get(),
                         stop_event=self._stop_flag)
            self._finish(book, d.store, cfg, fmts)
        except KeyboardInterrupt:
            # 用户按 Ctrl-C 关窗口等场景，engine 会保存断点后重抛
            self._q.put(("done", "已中断（断点已保存，重新点“开始抓取”即可续爬）"))
        except (RuleError,) as e:
            self._q.put(("fail", f"没有匹配的站点规则：{e}"))
        except Exception as e:  # noqa: BLE001
            self._q.put(("fail", f"{type(e).__name__}: {e}\n{traceback.format_exc()[-600:]}"))

    def _do_export(self, url, fmts):
        try:
            from .cli import load_book
            cfg = _config_from_args(self._args(url))
            book, store, rule = load_book(cfg, url, self._rules)
            self._tail_log(f"重新导出：{book.title}  [{rule.id}/{book.book_id}]")
            self._finish(book, store, cfg, fmts)
        except Exception as e:  # noqa: BLE001
            self._q.put(("fail", f"{type(e).__name__}: {e}"))

    def _prog(self, done, total, msg=""):
        """进度回调：**纯上报**，不做取消（取消由 engine 自己查 stop_event）。

        ⚠ 这里原来是 `if stop_flag: raise KeyboardInterrupt(...)` —— 那是**错的**：
        异常从 `as_completed` 循环抛出后，`with ThreadPoolExecutor(...)` 的 `__exit__`
        照样 `shutdown(wait=True)`，**等完所有已提交的章节才真正退出**。
        审计实测：第 3 章点停止 → 40/40 全抓完，而界面还提示「会在当前章节结束后停下」。
        现在改成把 `threading.Event` 交给 `engine.run(stop_event=...)`，由它在循环里
        `break` + `cancel_futures`。
        """
        self._q.put(("prog", (done, total, msg)))

    def _tail_log(self, s):
        self._q.put(("log", f"\n{s}"))

    def _finish(self, book, store, cfg, fmts):
        """校对 + 导出（复用 CLI 的同一套：proofread / export_all）。

        `fmts` 是**已在本线程外取好的 list**（见 _fmt_list 的注释）。
        """
        from .exporters import export_all, safe_out_dir
        from .proofread import format_report, proofread

        try:
            rep = proofread(book)
            self._tail_log(format_report(rep, max_items=8))
        except Exception as e:  # noqa: BLE001
            self._q.put(("log", f" ⚠ 校对报告生成失败（不影响导出）：{e}"))

        try:
            # ⚠ 目录名净化 + 越界断言（同 cli.py，见 safe_out_dir 注释）
            out_dir = safe_out_dir(cfg["save_dir"], book)
        except ValueError as e:
            self._q.put(("fail", str(e)))
            return
        try:
            paths = export_all(book, out_dir, formats=fmts,
                               verbose=lambda m, lv="": self._q.put(("log", "   " + m)))
        except Exception as e:  # noqa: BLE001
            self._q.put(("fail", f"导出失败：{type(e).__name__}: {e}"))
            return

        n_ok = sum(1 for c in book.chapters if c.status == "ok")
        n_prot = sum(1 for c in book.chapters if c.status in ("locked", "blocked"))
        self._q.put(("log", f"\n输出目录：{out_dir}"))
        for k, p in (paths or {}).items():
            self._q.put(("log", f" ✓ {k.upper()} → {p}"))
        self._q.put(("done", f"完成：{book.title} ｜ 可导出 {n_ok} 章"
                             + (f"，受保护 {n_prot} 章（零请求）" if n_prot else "")))


def main():
    try:
        app = App()
    except tk.TclError as e:
        print("无法启动图形界面（当前环境没有可用的 Tk）：\n  %s" % e, file=sys.stderr)
        print("请改用命令行：python -m noveldown --help", file=sys.stderr)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
