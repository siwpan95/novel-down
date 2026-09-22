# 发行版构建（packaging/）

把 novel-down 打成分发用的**便携版**与**安装版**。

## 一键构建

在本仓根目录执行：

```bat
F:/Python314/python.exe packaging/build.py --all
```

分步：

```bat
F:/Python314/python.exe packaging/build.py --portable          :: 便携版 onedir + onefile
F:/Python314/python.exe packaging/build.py --zip               :: onedir 压成 zip
F:/Python314/python.exe packaging/build.py --msi               :: MSI 安装版
F:/Python314/python.exe packaging/build.py --all --clean       :: 先清空 dist/ 与 build/
```

产物都在 `dist/`：

| 产物 | 形态 | 体积（实测） |
|---|---|---|
| `dist/noveldown/` | **便携版（目录）**：exe + `_internal`，解压即用 | 35 MB（zip 后 18 MB） |
| `dist/noveldown-onefile.exe` | **便携版（单文件）**：单个 exe | 18.6 MB（⚠ 启动约 **40 秒**，见下） |
| `dist/novel-down-0.8.39-win64.msi` | **MSI 安装版**：开始菜单、PATH、卸载项 | 见构建输出 |
| `dist/novel-down-0.8.39-setup.exe` | **EXE 安装器**：需 Inno Setup 编译 `inno.iss` | 本机未编译（见下） |

### ⚠ 单文件版（onefile）启动很慢 —— 实测约 40 秒

同一台机器上实测 `--version`：

| 形态 | 启动耗时 |
|---|---|
| **onedir** | **约 1.4 秒** |
| **onefile** | **约 40 秒**（第二、三次一样慢，**不是冷启动**） |

onefile 每次运行都要把 18MB 解包到临时目录，本机**杀毒软件会对解出来的文件做实时扫描**
（本机是腾讯电脑管家），开销几乎全在这。**这不是打包配置问题，是运行环境决定的。**

→ 建议：**日常用 onedir 版**；onefile 只适合「偶尔拿到别的机器上跑一下」的场景。

### 图形界面版（noveldown-gui）

```bat
F:/Python314/python.exe packaging/build.py --gui
```

产物 `dist/noveldown-gui/noveldown-gui.exe`（**windowed**，双击即开、不弹控制台）。

⚠ 两个与 CLI 版不同的处理：

- **不能排除 `tkinter`**（CLI 版排除它是为了省 ~10MB，GUI 版必须留着）；
- **只出 onedir、不出 onefile** —— onefile 每次启动要解包 + 被杀软扫描，实测 **约 40 秒**，
  对「双击就要看到窗口」的 GUI 完全不可接受。

⚠ GUI 版依赖打包用的 Python **自带 Tcl/Tk**（本机 `F://Python314` 自带 Tcl/Tk 9）。
用托管 Python（无 tcl/tk）打包会报 `tkinter installation is broken`。

## 端到端验证（实测通过）

用便携版真抓一本书（`dist/noveldown/noveldown.exe fetch ... --limit 3`）：

- 3 章 / 12071 字 / 受保护 0 章；
- 导出 TXT(35.9KB) · MD(36.2KB) · EPUB(23.1KB) 全部成功；
- 校对「广告残留 0」。

## 依赖与可选能力

发行版按**最小依赖**打包：`requests` + `beautifulsoup4` + `lxml`。

以下能力**不在**发行版里（缺了只会让对应站点不可用）：

- **浏览器路由**（目录靠 JS 渲染的站点，如起点）—— 需 `playwright` + Chromium 内核；
- **字体反爬解码**（番茄小说这类）—— 需 `fontTools` + `brotli`；
- **TLS 指纹伪装**（`--curl-cffi`）—— 需 `curl_cffi`。

要用这些请用**源码方式**运行（`pip install -r requirements.txt` + `python -m noveldown`）。
做「完整版」发行包只需去掉 `build.py` 的 `EXCLUDES` 里对应项。

## 五个踩过的坑（改打包脚本前必读）

1. **`--add-data` 必须用绝对路径**。相对路径会被解析成相对 `--specpath` 的目录，
   实测报 `Unable to find ...\build\noveldown\rules`。
2. **必须显式排除无关模块**。本机 `F:/Python314` 装了大量无关包，
   不排除会把 numpy / PIL / cryptography / curl_cffi / gevent / Cython / pygame 打进去
   → 产物 **110MB**；排除后 **35MB**。
3. **入口必须强制 UTF-8**。打包后 Windows 控制台 stdout 是 **GBK**，
   本项目输出大量 `⚠` `✓` `★`，不处理会直接
   `UnicodeEncodeError: 'gbk' codec can't encode '\u26a0'`。
   → 见 `entry_console.py` 顶部的 `reconfigure`，**换入口时必须保留**。
4. **规则是数据文件，打包器不会自动带**。
   `noveldown/rules/*.json`（161 条）+ `identities.json` 必须显式 `--add-data` / `include_files`。
5. **cx_Freeze 的 `build_exe` 目录要显式指定**。它构建前会清理该目录，
   已存在且删不掉时报 `the build_exe directory cannot be cleaned`。

## 关于 EXE 安装器（Inno Setup）

`inno.iss` 已写好，但**本机未编译**：

- Inno Setup 未安装；
- 外网下载被拦（实测 `files.jrsoftware.org` 只回 315 字节错误页）。

在有 `ISCC.exe` 的机器上执行即可：

```bat
ISCC.exe packaging\inno.iss
```

它与 MSI **共用同一个 UpgradeCode**，避免两种安装形态互相冲突。

## 未打包进发行版的东西

- `tools/`（开发用的扫描/探测脚本）、`tests/`、`docs/` —— 只含运行期需要的内容。
- 用源码运行才能用到 `tools/`（如 `scan_mirrors.py`、`hunt_api.py`）。
