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
| `enabled` | | 默认 `true`；`false` 则不进 `active_rules()` |
| `predecode` | | 默认 `true`。是否启用 JS 内联 base64 预解码 |
| `requires_js` | | 站点是否必须执行 JS 才能拿到内容。**本项目暂无 JS 引擎支持**，标 `true` 表示已知不可用 |
| `demo_url` | | 演示地址，会被第 1 层黑名单校验 |
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
| `sort` | 默认 `cid_numeric_asc`；另有 `cid_numeric_desc` |
| `volume_selector` | 可选卷标题选择器（会按文档顺序跟踪当前卷名） |

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
