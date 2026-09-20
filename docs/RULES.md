# 站点规则格式（RULES.md）

新增一个站点**只需加一个 JSON 文件**，不改代码。

```
noveldown/rules/<站点ID>.json
```

放进去即被 `load_rules()` 自动加载，启动时 `free_only`、必填字段、
付费站黑名单三项校验（见 [FREE_ONLY.md](./FREE_ONLY.md) 第 2 层）。

---

## 工作流

```bat
:: 1. 用探针看清站点结构
F:\Python314\python.exe tools\probe_site.py "https://新站点.com/book/123/"

:: 2. 照探针输出填 JSON
:: 3. 自检：抓目录 + 抽 1 章
F:\Python314\python.exe -m noveldown probe "https://新站点.com/book/123/"

:: 4. 上线
F:\Python314\python.exe -m noveldown fetch "https://新站点.com/book/123/" --limit 5
```

---

## 字段全表

### 顶层

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✓ | 规则 ID，建议用域名 |
| `name` | ✓ | 站点显示名 |
| `match` | ✓ | 域名数组（含别名，如 `["shuquge.com","xshuquge.net"]`） |
| `free_only` | ✓ | **必须为 `true`**，否则规则加载失败 |
| `enabled` | | 默认 `true`；`false` 则停用。停用规则只要求写 `disabled_reason`，不必写全选择器——它是「调研记录存根」 |
| `disabled_reason` | | 停用原因。**必须是技术原因**（WAF / 目录靠 JS / 需浏览器会话），不要写「因为含 VIP」——含 VIP 不构成拒绝理由，见 [FREE_ONLY.md](./FREE_ONLY.md) 第 1 层 |
| `predecode` | | 默认 `true`。是否启用 JS 内联 base64 预解码 |
| `fetch_mode` | | `http`（默认，纯 HTTP）\| `browser`（真实浏览器渲染后再取 DOM）。目录靠 JS 异步加载的站点用 browser |
| `browser` | | `fetch_mode=browser` 时的渲染参数：`wait_selector`（等某选择器出现）、`wait_ms`（额外固定等待）、`click_selectors`（先点这些元素，如「目录」标签）、`scroll`（滚到底触发懒加载） |
| `font_decode` | | 字体反爬解码配置（见下文「字体反爬」）。仅番茄这类站点需要 |
| `requires_js` | | 站点是否必须执行 JS 才能拿到内容。**本项目暂无 JS 引擎支持**，标 `true` 表示已知不可用 |
| `demo_url` | | 演示地址，会被第 1 层政策名单校验 |
| `notes` | | 逆向记录（踩过的坑写这里，便于后人维护） |

### `book`

| 字段 | 说明 |
|---|---|
| `url_pattern` | 从书籍 URL 提取 `bid` 的正则，**捕获组 1 即 bid** |
| `info_url` | 书籍页 URL 模板，支持 `{origin}` `{bid}` `{url}` |
| `title` / `author` / `intro` / `cover` / `status` | 候选 CSS 选择器**数组**，按序取第一个命中；`meta[...]` 取 `content` 属性，其余取文本 |

### `catalog`

| 字段 | 说明 |
|---|---|
| `pages.mode` | `single`（单页目录）\| `auto`（迭代展开，**推荐**）\| `select` \| `links` \| `template` |
| `pages.option_selector` | 默认 `select option`；`auto`/`select` 模式下读取分页 |
| `pages.value_attribute` | 默认 `value` |
| `pages.keep_pattern` | 只保留 value 含该串的 option（支持 `{bid}`） |
| `pages.link_pattern` | `auto`/`links` 模式：匹配目录页跳转链接的正则（支持 `{bid}`） |
| `pages.max_pages` | 目录页上限，默认 80 |
| `pages.max_rounds` | 迭代轮数上限，默认 4 |
| `item_selector` | 章节项 `<a>` 的 CSS 选择器 |
| `id_from.mode` | `href`（从链接取）\| `onclick`（从 onclick 取） |
| `id_from.pattern` | 必须含 **命名捕获组 `(?P<cid>...)`** |
| `url_template` | 可选。支持 `{origin}` `{bid}` `{cid}`；不填则 `urljoin(页面URL, href)` |
| `sort` | `cid_numeric_asc`（默认，ID 即顺序号）\| `document_order`（保持页面顺序，用于雪花 ID 站点）\| `cid_numeric_desc` |
| `dedupe` | `keep_first`（默认）\| `keep_last`（回显在**列表头部**时用它，见下） |
| `volume_selector` | 可选卷标题选择器（会按文档顺序跟踪当前卷名） |

> **`document_order` + `keep_last` 的用途**（番茄小说的形态）：目录第一项是
> 「最近更新：第966章 终章（完）」回显，与列表末尾的正文条目**同 cid**。
> 章节 ID 是雪花 ID，用 cid 升序会把回显那条排到最后、并且标题带着「最近更新：」。
> 用 `document_order` + `keep_last` 即可丢掉头部回显、保住末尾那条干净条目。

### `chapter`

| 字段 | 说明 |
|---|---|
| `title_selector` | 可选。正文页标题（会自动剥离「（第N页）」后缀） |
| `content_selector` | ✓ 正文容器 CSS |
| `strip_selectors` | 需从容器内剔除的元素（导航 / 标题 / 脚本 / 水印） |
| `next_page.selector` | 分页导航链接选择器 |
| `next_page.text_contains` | 链接文案必须含该串（如 `下一章`） |
| `next_page.continue_when` | `same_base_id`：仅当链接的 cid 与当前章节相同才续页 |
| `next_page.href_pattern` | 从链接提取 cid 的正则（含 `(?P<cid>...)`） |
| `ad_patterns` | 广告行特征数组，命中即丢弃该行 |

---

## 目录归一化算法（为什么规则可以写得很懒）

引擎对目录一律执行 **「先全收集 → 按 cid 去重 → 按 cid 升序编号」**。
这一步统一解决三类反爬，规则无需为它们写特例：

| 反爬手法 | 实例 | 归一化如何消解 |
|---|---|---|
| **最新章节倒序回显** | shuquge 目录首 12 项是倒序的最新章 | 与正文列表 cid 重复 → 去重丢弃 |
| **CSS 隐藏列表项** | bqgbe `.section-list.ycxsid>li:nth-child(1..15){display:none}` | 隐藏项仍被收集，但都是回显 → 去重丢弃 |
| **多页目录拼接** | bqgbe 3 页 / biqu520 27 页 | 三页并集去重后即全量目录 |

实测校验：

| 站点 | 原始条目 | 归一化后 | 说明 |
|---|---|---|---|
| shuquge.com | 1594 | **1582** | 恰好剔除 12 项回显 |
| bqgbe.cc | 320（3 页） | **169** | 与全量并集一致 |
| biqu520.net | 2753（27 页） | **2653** | 与站点自报分页 `第1-100章…第2601-2652章` 完全吻合 |

**前提**：站点的章节 ID 与阅读顺序同向。已核验的三个站均满足
（如 bqgbe `54948`=第 1 章 … `55351`=第 190 章）。
若某站 ID 无序，需给该规则加自定义排序逻辑（目前未遇到）。

---

## 实例：三种典型形态

### A. 标准笔趣阁单页目录（shuquge.com）

```json
{
  "id": "shuquge.com", "free_only": true, "predecode": false,
  "match": ["shuquge.com", "xshuquge.net"],
  "book": {
    "url_pattern": "/txt/(\\d+)/",
    "info_url": "{origin}/txt/{bid}/index.html",
    "title": ["meta[property='og:novel:book_name']"]
  },
  "catalog": {
    "pages": {"mode": "single", "url": "{origin}/txt/{bid}/index.html"},
    "item_selector": "div.listmain dl dd a",
    "id_from": {"mode": "href", "pattern": "(?P<cid>\\d+)\\.html"}
  },
  "chapter": {
    "content_selector": "div#content",
    "strip_selectors": ["div#center_tip", "script", "style"],
    "ad_patterns": ["最新网址", "请记住本站", "xshuquge"]
  }
}
```

> 关键坑：`div#content` 首位嵌 `<div id="center_tip">最新网址…</div>`，
> 不剔除会因 `</div>` 提前闭合而**只抓到水印本身**（实测只拿到 21 字）。

### B. base64 内联正文 + 章节分页（bqgbe.cc）

```json
{
  "id": "bqgbe.cc", "free_only": true, "predecode": true,
  "match": ["bqgbe.cc"],
  "catalog": {
    "pages": {
      "mode": "auto",
      "option_selector": "select option",
      "keep_pattern": "/txt/{bid}/",
      "link_pattern": "/txt/\\d+/ml\\d+\\.html"
    },
    "item_selector": "ul.section-list li a",
    "id_from": {"mode": "href", "pattern": "/txt/\\d+/(?P<cid>\\d+)(?:_\\d+)?\\.html"}
  },
  "chapter": {
    "content_selector": "div.word_read",
    "strip_selectors": ["h2.layout-tit", "h3", "div.read_btn", "script", "style"],
    "next_page": {
      "selector": "div.read_btn a",
      "text_contains": "下一章",
      "continue_when": "same_base_id",
      "href_pattern": "/txt/\\d+/(?P<cid>\\d+)(?:_\\d+)?\\.html"
    }
  }
}
```

> 两个关键坑：
> ① 正文按段 base64 藏在 `<script>document.writeln(随机名.随机名('…'))</script>`，
> 必须 `predecode: true`，且还原后要**拆掉 script 壳**（否则解析器不认内部 `<p>`）。
> ② 站点把**续页**链接误标成「下一章」——`54948.html` 的「下一章」指向 `54948_1.html`。
> 靠 `continue_when: same_base_id` 判定：cid 相同才是续页，不同就是真的下一章。

### C. 无 href 的 onclick 目录（biqu520.net）

```json
{
  "id": "biqu520.net", "free_only": true, "predecode": true,
  "match": ["biqu520.net"],
  "book": {"url_pattern": "/books_(\\d+)/", "info_url": "{origin}/books_{bid}/"},
  "catalog": {
    "pages": {"mode": "auto", "link_pattern": "/chapters_\\d+/\\d+"},
    "item_selector": "ul.section-list li a",
    "id_from": {"mode": "onclick", "pattern": "(?P<cid>\\d+)"},
    "url_template": "{origin}/books_{bid}/{cid}.html"
  },
  "chapter": {
    "content_selector": "div.word_read",
    "strip_selectors": ["h2.layout-tit", "h3", "div.read_btn", "script", "style"],
    "next_page": {
      "selector": "div.read_btn a", "text_contains": "下一章",
      "continue_when": "same_base_id",
      "href_pattern": "/books/\\d+/(?P<cid>\\d+)\\.html"
    }
  }
}
```

> 目录项是 `<a onclick="随机函数名(章节ID);">`，**没有 href**，
> 函数名每次渲染都变（实测见过 `fwbnh` / `ouiigwv`），所以只能匹配
> `函数名(数字)` 这个形状；URL 由 `url_template` 拼出。

### D. 字体反爬 + 雪花 ID 目录（fanqienovel.com）

**正版**站点（番茄小说是字节旗下「免费阅读 + 广告」平台，全站无 VIP 章节）。

```json
{
  "id": "fanqienovel.com", "free_only": true, "predecode": false,
  "match": ["fanqienovel.com"],
  "book": {
    "url_pattern": "/page/(\\d+)",
    "info_url": "{origin}/page/{bid}",
    "title": ["h1"],
    "author": ["div.author-name"],
    "intro": ["meta[name='description']"]
  },
  "catalog": {
    "pages": {"mode": "single", "url": "{origin}/page/{bid}"},
    "item_selector": "a[href^='/reader/']",
    "id_from": {"mode": "href", "pattern": "/reader/(?P<cid>\\d+)"},
    "sort": "document_order",
    "dedupe": "keep_last"
  },
  "chapter": {
    "title_selector": "h1.muye-reader-title",
    "content_selector": "div.muye-reader-content",
    "strip_selectors": ["script", "style"]
  },
  "font_decode": {"mode": "outline_match", "auto_build": true}
}
```

### E. 正版站 + VIP 混排目录（zongheng.com）——「站点含 VIP ≠ 不可用」

这是**最能说明本项目设计取向**的一条规则：一本 705 章的正版小说，其中 **650 章是 VIP**。
但前 50 章免费内容在射程内，VIP 章靠**目录层的 class 标记**拦下。

```json
{
  "id": "zongheng.com", "free_only": true, "predecode": false,
  "match": ["zongheng.com", "huayu.zongheng.com", "read.zongheng.com"],
  "book": {
    "url_pattern": "/(?:book|showchapter|info|chapter)/(\\d{5,})",
    "info_url": "https://book.zongheng.com/book/{bid}.html",
    "title": [".book-info .book-name", "h1"],
    "author": [".au-name", ".book-author .au-name"],
    "intro": ["meta[name='description']"]
  },
  "catalog": {
    "pages": {"mode": "auto", "link_pattern": "/showchapter/\\d+\\.html"},
    "item_selector": "ul.chapter-list li a",
    "id_from": {"mode": "href", "pattern": "/chapter/\\d+/(?P<cid>\\d+)\\.html"},
    "sort": "cid_numeric_asc"
  },
  "chapter": {
    "title_selector": "div.reader-content div.title",
    "content_selector": "div.reader-content div.content",
    "strip_selectors": ["div.reader-content div.title",
                        "div.reader-content div.bookinfo", "script", "style"]
  }
}
```

关键实测发现：

1. **站点跨三个子域，只有一处有完整目录**：

   | 地址 | 结果 |
   |---|---|
   | `huayu.zongheng.com/showchapter/{bid}.html` | **700 章 + 650 个 `li.vip`** ✅ |
   | `book.zongheng.com/showchapter/{bid}.html` | 只有 1 章（最新章节试读） |
   | `www.zongheng.com/showchapter/{bid}.html` | 同样只有 1 章 |

   所以 `info_url` 指向书籍页，再用书籍页的 `<a class="all-catalog">` 由
   `pages.mode=auto` + `link_pattern` 自动跳到 huayu 目录。

2. **VIP 标记在 `<li>` 上，不在 `<a>` 上**：`<li class="vip col-4">`。
   本项目第 3 层会检查**父元素**的 class（`is_vip_item(cls + parent_cls, title)`），
   所以能命中——若只查 `<a>` 自身的 class 就会漏掉全部 650 章。

3. **免费章与 VIP 章的正文差异**（第 4 层是第二道保险）：

   | | 段数 | 字数 | 付费墙特征 |
   |---|---|---|---|
   | 免费章 | 51 | 3177 | 无 |
   | VIP 章 | 6 | 233 | 命中「请先登录」 |

4. **正文不在 `div.reader-content` 直接子级**，而是在其内的 `div.content`；
   `div.title` / `div.bookinfo` 要剔除，否则章节标题与作者行会混进正文。

5. 这条规则**没走浏览器路由**：目录与正文都是服务端渲染，纯 HTTP 可取（240KB）。
   用无头浏览器反而只看到 2 个章节链接。**先用实测证据决定路由。**

---

## 浏览器路由（`fetch_mode: browser`）

有些站点的目录/正文由 JS 异步加载，纯 HTTP 只能拿到首屏骨架。此时把 `fetch_mode`
设为 `browser`，引擎会用真实 Chromium 渲染后再取 DOM：

```json
{
  "fetch_mode": "browser",
  "browser": {
    "wait_selector": "ul.chapter-list li a",
    "wait_ms": 3000,
    "click_selectors": ["a.all-catalog"],
    "scroll": false
  }
}
```

要点：

- **可选依赖**：需要 `playwright` + Chromium（`python -m playwright install chromium`）。
  没装只影响这类站点，其它规则照常工作，并会给出带安装命令的提示。
- **强制单线程**：Playwright 同步 API 不能跨线程共享，故 browser 模式下并发自动降为 1
  （引擎会打印说明）。速度会明显慢于 HTTP 路由。
- **不参与任何凭据环节**：不注入 Cookie、不登录、不接管你的浏览器会话。
  若站点要求完成人机验证（captcha），本路由同样会失败——那是需要人参与的步骤，
  代码里不做绕过。
- **先试 HTTP 再上浏览器**：实测有反直觉的情况——纵横的 `showchapter` 页用无头浏览器
  打开只看到 2 个章节链接（JS 版是懒加载的），而**纯 HTTP 取到的静态 HTML 里有完整
  700 章**。所以不要默认"JS 站就得用浏览器"，先用 `probe_site.py` 与
  `python -m noveldown probe` 各试一次，用实测证据决定。

---

## 字体反爬（`font_decode`）

某些站点把正文里的字符替换成**私用区码位**（U+E000–U+F8FF），再用一份自定义字体
把这些码位渲染成真字形。DOM 源码里是 `'寒\ue516呼啸'`，浏览器里显示「寒风呼啸」。

**这个坑最危险的地方是它不报错**：文本能取到、结构正常、字数也对，只是**缺字乱码**。
实测番茄小说第 1 章 1409 字里有 **764 个 PUA（54%）**，连 `<meta description>`
都是混淆过的——页面上没有任何非混淆来源。

### 为什么不能简单反查

子集字体里**没有**现成映射线索：

| 思路 | 实测结果 |
|---|---|
| 读 cmap | 362 个码位**全是 PUA**，零真实码位 |
| 读 glyph 名 | 形如 `gid58646`，取自来源字体的序号，与官方字体的 gid/cid **都不一致** |
| 比 charstring 字节日码 | 子集重新打包过，0/363 命中 |
| 找页面其他位置的明文 | 无（meta / JSON-LD 同样被混淆），也无明文 API |

### 可行方法：字形轮廓匹配

子集字体的 CFF charstring 就是来源字体的**字形轮廓**。拿到**同版本**参考字体后，
把两者每个字形的轮廓点集序列化取哈希即可精确对应（不是 OCR 近似）：

```python
from fontTools.pens.recordingPen import RecordingPen
pen = RecordingPen(); glyph_set[name].draw(pen)
key = ";".join(op + "|" + ",".join(f"{x:g}/{y:g}" for x, y in pts)
               for op, pts in pen.value)   # → sha1(key)
```

**版本必须严格对上**（实测）：

| 参考字体版本 | 命中率 |
|---|---|
| `adobe-fonts/source-han-sans@2.002R`（与子集声明一致） | **363/363** |
| `@release`（2.005） | 7/363 |

还有一个取号陷阱：**同一字形可能对应多个码位**（「风」U+98CE 与康熙部首「⻛」U+2EDB
共用字形）。不做区块优先级时，`U+E516` 会反查成 `⻛` 而不是 `风`。
`fontdecode._cp_priority()` 按 CJK 基本区 > 扩展A > 扩展B > 标点 > 全角 > 部首 取号。

### 使用

```bat
:: 一次性：下载参考字体（约 17MB）并生成轮廓索引（缓存在 output/fontcache/）
F:\Python314\python.exe tools\build_fontmap.py

:: 之后 fetch / probe 会自动用上；规则里 auto_build=true 时首次也会自动构建
F:\Python314\python.exe -m noveldown probe "https://fanqienovel.com/page/<bookId>"
```

依赖：`fontTools`（+ `brotli`，读 woff2 时需要）。**只影响这类站点**，
缺失时其它站点照常工作，并会给出带 pip 命令的明确提示。

> 参考字体**不随仓库分发**（OFL-1.1 开源字体，17MB；索引约 1.2MB 也只在本地缓存），
> 由脚本按需下载并校验 sha256。理由见 [REFERENCE.md](./REFERENCE.md)。

---

## 调试技巧

```bat
:: 看规则是否加载、字段取值
F:\Python314\python.exe -m noveldown rules

:: 单站规则自检（抓目录 + 抽 1 章，打印每一环的命中数）
F:\Python314\python.exe -m noveldown probe "URL"

:: 未知站点的原始结构（select / 链接形状 / 正文容器候选 / base64 命中）
F:\Python314\python.exe tools\probe_site.py "URL"
```

离线回归测试：

```bat
F:\Python314\python.exe -m unittest discover -s tests -t .
```

新增规则后建议把该站的**目录页与章节页各存一份**到 `tests/fixtures/`，
并按 `tests/test_parser.py` 的样式补一个回归用例——站点改版时能立刻发现。
