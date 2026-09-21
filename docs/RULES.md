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
python tools\probe_site.py "https://新站点.com/book/123/"

:: 2. 照探针输出填 JSON
:: 3. 自检：抓目录 + 抽 1 章
python -m noveldown probe "https://新站点.com/book/123/"

:: 4. 上线
python -m noveldown fetch "https://新站点.com/book/123/" --limit 5
```

### 规则文件放哪

```
noveldown/rules/                 手工维护的规则（一站点一文件）—— 站点有自己的形态，值得逐个精读
noveldown/rules/mirrors/         **批量铺开的镜像池**（自动聚类生成，见 §11.3/§11.4 of NEW_SITES_PLAN）
```

加载器**递归**读子目录（`noveldown.rules.iter_rule_files`）。
镜像池之所以单独放一层：它是「一个模板一个文件」自动产出的，数量会到**几百条**，
与手写规则混在同一层会让 `rules/` 完全没法看。

⚠ 镜像池里的每条规则，其 `match` 中的域名都经过**逐域实测**
（目录 ≥20 章 + 正文 ≥300 字）并用**真实引擎复验过**（`tools/verify_mirror_rules.py`），
不是按模板猜的 —— 详见 `docs/NEW_SITES_PLAN.md §11.4`。

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
| `fetch_mode` | | `http`（默认，纯 HTTP）\| `browser`（真实浏览器渲染后再取 DOM）。目录靠 JS 异步加载的站点用 browser。**可被段内覆盖**，见下 |
| `book.fetch_mode` / `catalog.fetch_mode` / `chapter.fetch_mode` | | 可选。**逐段覆盖**顶层 `fetch_mode`（非法值加载即报错）。让「书籍页/目录必须浏览器、正文纯 HTTP」这类站点拿到该有的速度与并发——见下面「分段路由」一节 |
| `browser` | | `fetch_mode=browser` 时的渲染参数：**`wait_selector`**（等待条件，见下）、`wait_ms`（额外固定等待）、**`nav_retries`**（导航瞬时失败的重试总次数，1~8，默认 4，带 `1.2s×n` 退避）、`click_selectors`（先点这些元素，如「目录」标签）、`scroll`（滚到底触发懒加载）、**`anti_detect`**（反检测模式，见「浏览器路由」一节）、`channel`（默认 `chrome`）、`args`（追加启动参数）、`stealth_js`（可选自备 stealth 脚本路径） |
| `browser.wait_selector` | | 等待条件，两种写法：**字符串** = 所有页面角色共用（历史行为）；**对象** = `{"book": …, "catalog": …, "chapter": …}` 逐角色指定，未出现的角色 / 值为 `null`·`false`·`""` = **不等待**。⚠ 强烈建议用对象写法——字符串是全角色广播，把**章节容器**写成字符串会让**书籍页**也去等它，白等满超时才继续（实测速读谷目录耗时 37s，其中 30s 纯浪费） |
| `font_decode` | | 字体反爬解码开关：`{"enable": true}`（默认 `true`）。解码途径由字体自身决定（glyph 名优先，否则随仓轮廓索引）。见下文「字体反爬」 |
| `requires_js` | | 该站点内容需执行 JS 才能拿到（与 `fetch_mode=browser` 配套）。**纯展示标记**：`sites`/`rules` 命令会显示「[需JS]」，不参与判定 |
| `demo_url` | | 演示地址，会被第 1 层政策名单校验 |
| `notes` | | 逆向记录（踩过的坑写这里，便于后人维护） |

### `book`

| 字段 | 说明 |
|---|---|
| `url_pattern` | 从书籍 URL 提取 `bid` 的正则，**捕获组 1 即 bid** |
| `info_url` | 书籍页 URL 模板，支持 `{origin}` `{bid}` `{url}` |
| `title` / `author` / `intro` / `cover` / `status` | 候选 CSS 选择器**数组**，按序取第一个命中；`meta[...]` 取 `content` 属性，其余取文本。特殊值 **`@title`** = 文档 `<title>` 文本，**`sel@attr`** = 取元素属性（`a.book-face img@src`）。⚠ `@` 只认**末尾**的 `@名字` 形式，`a[href*='@']` 这类属性选择器里的 `@` 不会被拆 |
| `info_api` | 可选。书籍页是 SPA 外壳、简介/封面另由 **XHR 片段**下发时用它：`{"url": "{origin}/book/bookintro?bid={bid}", "intro": [...], "cover": [...]}`。`url` 必填；可覆盖 `title`/`author`/`intro`/`cover`/`status`。**片段里声明的字段优先**，取不到（或整条请求失败）就回落主页面选择器 —— 元数据缺失不该升级成整本书失败。⚠ 反面教材：书山书籍页的 `meta[name=description]` 是**站点通用文案**（每本书一模一样），拿它当简介等于往 EPUB 里写错数据。<br>**片段也可以是 JSON/JSONP**（v0.8.15）：此时字段用 `"@json:data.{bid}.name"` 写路径（`{bid}` 会被替换，因为有些接口把书 ID 当键），JSONP 包装 `cb({...})` 与纯 JSON 两种都吃 |
| `title_pattern` | 可选正则，对 `title` 结果做清洗（如 `^(.*?)(?:免费阅读|最新章节)` 去掉站点后缀） |
| `@json:<path>` | `book.title`/`author`/`intro`… 的**特殊取值**：从页面的 SSR 数据块（默认 `script#__NEXT_DATA__`，可用 `book.json_source` 改）按 `a.b.c` 路径取字段。Next.js/Nuxt 站的书名/作者常只在数据块里（次元姬） |
| `author_pattern` | 可选正则，对 `author` 结果做清洗/抽取（书海书名与作者同格：`神农医婿 作者: 方长` → `作者[:：]\s*(.+?)\s*$`） |
| `author_pattern_strict` | 可选布尔（v0.8.16）。`author_pattern` **不匹配时把作者置空**，而不是保留原值。用于「标题里恰好带作者才取、否则宁可为空」的文库型站点 —— 虚阁网的 `<title>` 有`红楼梦\|曹雪芹_虚阁网`（带作者）与 `外国畅销书_虚阁网`（不带）两种形态，不开严格模式会把**整条 title 当作者名** |

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
| `mode` | `html`（默认）\| `json_api`（目录来自 JSON 接口，见下） |
| `json.json_source` | 可选。**JSON 嵌在 HTML 里**时的容器 CSS（Next.js `<script id="__NEXT_DATA__">`、Nuxt `__NUXT__`）：先取出那段 JSON，再照常按 `items_path` 取值 → 一条规则吃下整类 SSR 站 |
| `json` | `json_api` 模式的配置：`url`（模板，支持 `{origin}/{bid}` 与 `{cookie:NAME}` 占位符）、`items_path`（如 `data.chapters`）、**`flatten_field`**（卷→章嵌套展开，如 `cs`）、`cid_field`、`title_field`、**`vip_field`**、`vip_truthy` |
| `json.max_pages` / `page_from` | **JSON 目录分页**（v0.8.15）。`url` 里写 `{page}` 即在多页之间迭代（`page_from` 默认 1），某页返回空即停。⚠ `{page}` 却不配 `max_pages>1` → **加载即报错** —— 因为这种配置**不会报错、只会少抓章节**（实测仙人掌小说：单页上限 20 章，而书有 490 章） |
| `json.api_url_field` | 可选。逐章**正文地址**（不透明、无法由 bid/cid 推导）所在的字段路径。取到的地址会带在目录条目上，供 `chapter.body_api.url` 的 **`{api_url}`** 与 `catalog.url_template` 消费（实测仙人掌小说每章一个 `zm.news.so.com/<hash>`） |
| 字段路径可**嵌套**，且自动穿透**字符串化的 JSON** | `cid_field`/`title_field`/`vip_field`/`api_url_field` 一律按 `a.b.c` 取值。有些接口把子对象**序列化成字符串**塞进字段（`op_ext` = `'{"money_topic":{...}}'`）—— 写成 `op_ext.money_topic.title` 会**自动穿透**。⚠ 反过来要小心：这类接口的**页内序号**（`idx`）不是全局章节号，别拿它当 cid |
| `item_selector` | 章节项选择器（`html` 模式必需）。**也可选中容器**：此时 href 从内嵌 `<a>` 取、**标题取容器文本**（书海 33% 的 `<a>` 文本为空，只选 `<a>` 会丢标题） |
| `id_from.mode` | `href`（从链接取）\| `onclick`（从 onclick 取） |
| `id_from.pattern` | 必须含 **命名捕获组 `(?P<cid>...)`** |
| `url_template` | 可选。支持 `{origin}` `{bid}` `{cid}`；不填则 `urljoin(页面URL, href)`。⚠ 目录与书籍页**不在同一子域**时必须写**绝对 URL** —— 逐浪的目录在 `book.zhulang.com/{bid}/`，而 `{origin}` 会解析成书籍页的 `www.zhulang.com` |
| `browser_wait_selector` | 可选。**目录页**专用的浏览器等待条件。优先级**高于**顶层 `browser.wait_selector` 的角色值；写 `false` / `""` 表示该页**明确不等待** |
| `sort` | `cid_numeric_asc`（默认，ID 即顺序号）\| `document_order`（保持页面顺序，用于雪花 ID 站点）\| `cid_numeric_desc` |
| `dedupe` | `keep_first`（默认）\| `keep_last`（回显在**列表头部**时用它，见下） |
| `continuation_title_pattern` | 可选。**多页章回的续页合并**（v0.8.16）。古籍/文库站常把一章拆成多页，而**续页没有自己的标题**、只写一个页码标记（实测虚阁网：`001`=`第一回…(1)`、`002`=`(2)`、`003`=`(3)`）。传一个正则（如 `^[（(]\\d+[）)]$`）即启用：标题匹配的条目**并入前一条**、不新增章，其 URL 收进前一章的 `extra_pages`，由引擎顺序抓完再拼装。<br>· 实测效果：**277 章（含 156 个假章）→ 121 章**（红楼梦 = 作者简介 + 120 回）。<br>· ⚠ **为什么用目录而不是页内「下一页」链接**：页尾「下一页」既可能是续页也可能是下一回，靠它判断要猜；目录页自己标了 `(2)`/`(3)` 是**权威信号**。（若改走页内链接，必须有可靠停止判据，否则会**一路把整本书拼成一章**。）<br>· ⚠ **受保护的续页只丢弃、不收 URL** —— 绝不因拼装而多请求 VIP 页。<br>· 校验（加载即报错）：空模式 / 非法正则 / 能匹配空串 / 能匹配常见标题样本 —— 过宽的模式会**静默少章** |
| `volume_selector` | 可选卷标题/分段选择器（按文档顺序跟踪当前卷名；**目录按分段标注免费/VIP 时也用它**） |
| `vip_volume_markers` | 可选。**所属分段**名命中这些词即判受保护（塔读 `<h2><span>免费章节<i>/N章</i></span></h2>`）。需配 `volume_selector` |
| `vip_child_selector` | 可选。VIP 标记在目录项的**子元素**上时用它（书海 `<div class="chapter-item"><a …>…</a><span class="vip"></span></div>`）。判定范围 = 项自身 + **链接元素的父级** |

> **`document_order` + `keep_last` 的用途**（番茄小说的形态）：目录第一项是
> 「最近更新：第966章 终章（完）」回显，与列表末尾的正文条目**同 cid**。
> 章节 ID 是雪花 ID，用 cid 升序会把回显那条排到最后、并且标题带着「最近更新：」。
> 用 `document_order` + `keep_last` 即可丢掉头部回显、保住末尾那条干净条目。

### `chapter`

| 字段 | 说明 |
|---|---|
| `title_selector` | 可选。正文页标题（会自动剥离「（第N页）」后缀） |
| `browser_wait_selector` | 可选。**章节页**专用的浏览器等待条件。优先级**高于**顶层 `browser.wait_selector` 的角色值；写 `false` / `""` 表示明确不等待。⚠ **只放"内容就绪"那一支**：`wait_for_selector` 是 OR 语义，塞入骨架期即命中的宽松选择器会导致提前放行 |
| `body_api` | 正文来自 **JSON 接口**时的配置（塔读：章节页是空壳）。`url` 支持 `{origin}/{bid}/{cid}/{seq}`（seq = 章节序号，从 1 起）与 **`{api_url}`**（逐章地址由 `catalog.json.api_url_field` 带下来）；`content_field` 取字段；`drop` 按 `equals_base64_of: cid` 剔除站点水印段。取到的 HTML 会被包成 `div.nd-api-body`，后续选择器照常用 |
| `body_api.require` | 可选。**在数据源上判免费**（v0.8.15，本仓最关键的红线防线之一）。`{"field": "data.unlock"}`：响应里该字段**取到且落在 `truthy`（默认 1/true/yes）里**才算通过，否则该章判 **blocked、不导出**。<br>⚠ 为什么必须有它：实测仙人掌小说（360）的付费章走正文接口**既不报错、也不给任何付费提示**，只返回一段**戛然截断的试读片段**（642 字符 vs 完整 2392 字符），正文里连一个「付费/VIP」字样都没有 → **第 4 层「付费墙特征词」完全失效**，会把试读**静默**当正文导出。而同一响应里有 `unlock: false` 这种权威状态字段，直接拿它判最可靠。<br>语义：字段缺失/null/假值 → 判受保护（宁可漏抓一章，可见可重试）；**完全不是 JSON → 不判**，交下游兜底（否则会把免费章误标 locked 而丢内容） |
| `content_selector` | ✓ 正文容器 CSS（用 `body_api` 时填 `div.nd-api-body`） |
| `content_selectors` | 可选**候选列表**（同一站不同请求可能给不同容器；按序取第一个命中） |
| `drop_leading_title_paragraph` | 可选布尔。正文首段**就是标题行**、且该元素无 class 可剔时（飞卢 `div.noveContent > p:first`）开启；**仅当首段与目录标题完全相同**时才删除 —— 宁可不删，也不吃掉真正的首段 |
| `paragraph_selector` | 可选。**按段落元素逐个取文本**，而非整块容器文本。用于 `<p>` 里混着段评数/点赞数等附加节点的站点（如起点 `span.content-text`）。**未命中时会自动回退为容器整体切分**，并把原因写进章节备注（`extract_note`），避免整章静默变空。⚠ 也用于「容器选对了、但里面混着导航」的站点 —— 潇湘书院 `div#reader-content` 里混了登录条 + 底部菜单 + 面包屑（容器 2400 汉字 / 正文 2164），逐浪 `div#read-content` 前面挂着 `div.textinfo`（小说/作者/更新时间/字数）。这类站改 `paragraph_selector` 即可，**不必硬凑 `strip_selectors`**：只要导航不在 `<p>` 里，逐段取就天然排除 |
| `strip_selectors` | 需从容器内剔除的元素（导航 / 标题 / 脚本 / 水印） |
| `vip_markers` | 可选。**整页**付费特征词/类名（付费信号不在正文里、而在 CSS 文件名或页面元素上的站点，如 17K 的 `chapter_vip`） |
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

## 实例：十三种典型形态

A–H 覆盖从「标准免费站」到「反检测浏览器 + JSON 接口目录」的全部难度梯度。
新增站点时，先在本节找最接近的一条照抄，再改选择器。

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
  "font_decode": {"enable": true}
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

### F. JSON 接口目录 + 浏览器过 WAF（qimao.com）

**正版**「免费阅读 + 广告」平台。目录不在 HTML 里，而在 JSON 接口；站点又有阿里云 WAF。

```json
{
  "id": "qimao.com", "free_only": true, "fetch_mode": "browser",
  "match": ["qimao.com"],
  "book": {
    "url_pattern": "/shuku/(\\d+)",
    "info_url": "{origin}/shuku/{bid}/",
    "title": ["@title", ".title"],
    "title_pattern": "^(.*?)(?:免费阅读|最新章节)"
  },
  "browser": {"wait_ms": 1200},
  "catalog": {
    "mode": "json_api",
    "json": {
      "url": "{origin}/qimaoapi/api/book/chapter-list?book_id={bid}",
      "items_path": "data.chapters",
      "cid_field": "id", "title_field": "title",
      "vip_field": "is_vip", "vip_truthy": ["1", "true"]
    },
    "url_template": "{origin}/shuku/{bid}-{cid}/",
    "sort": "document_order"
  },
  "chapter": {
    "title_selector": "h2.chapter-title",
    "content_selector": "div.chapter-detail-wrap-content",
    "browser_wait_selector": "div.chapter-detail-wrap-content"
  }
}
```

关键实测发现：

1. **目录接口带逐章 `is_vip`** —— 比 HTML class 更可靠，第 3 层据此判定、连请求都不发。
   实测该书 708 章：`is_vip=0` 只有 **20 章**，其余 688 章是 `1`。
2. **`is_vip=1` 不是付费墙，是 APP 墙**：web 端把这些章的正文替换成
   「下载【七猫免费小说APP】，继续在APP内免费畅读全本内容」。
   那段占位文字 **78 字 > 最小字数阈值 50** —— 不显式拦截就会被当成正常正文存下来。
   → 第 4 层已补「APP 墙」特征词（见 `constants.PAYWALL_MARKERS`）。
3. **接口必须带 `Accept: application/json`**：只带 `Referer` 仍会被回 23670 字节的
   SPA 外壳（首字符是 `<`，不是 `{`）。
4. **站点有阿里云 WAF**（`acw_tc` / `acw_sc__v2`）：纯 HTTP 拿不到数据，
   用浏览器跑一次 WAF 的 JS 后就放行 → `fetch_mode: browser`。
   浏览器路由下**取 JSON 必须用页面内 `fetch()`**，不能用 `page.goto`
   （Chrome 会把 JSON 包成 `<pre>` 的 HTML 文档，破坏解析）。
5. **书名只在 `<title>` 里**（SPA），且带「免费阅读-七猫中文网」后缀 →
   用 `@title` + `title_pattern` 清洗。

### G. 浏览器路由 + 站点级 VIP 特征（17k.com）

**正版**站点，阿里云 WAF（`acw_tc` / `acw_sc__v2`）→ 需浏览器路由。
实测《师弟，你的丹药太不正经了》586 章**全免费**。

```json
{
  "id": "17k.com", "free_only": true, "fetch_mode": "browser",
  "match": ["17k.com"],
  "book": {"url_pattern": "/(?:book|list|chapter)/(\\d+)",
           "info_url": "{origin}/book/{bid}.html",
           "title": ["@title"], "title_pattern": "^(.*?)_"},
  "browser": {"wait_ms": 2500},
  "catalog": {
    "pages": {"mode": "single", "url": "{origin}/list/{bid}.html"},
    "item_selector": "dl.Volume dd a[href*='/chapter/']",
    "id_from": {"mode": "href", "pattern": "/chapter/\\d+/(?P<cid>\\d+)\\.html"},
    "browser_wait_selector": "dl.Volume dd a[href*='/chapter/']"
  },
  "chapter": {
    "content_selectors": ["div#readAreaBox", "div.readAreaBox", "div#readArea"],
    "browser_wait_selector": "div.readAreaBox, div#readAreaBox, div#readArea",
    "strip_selectors": ["h1", "h2", ".chapter_update_time", ".chapter_text_ad",
                        ".read_tit", ".nextChapter", ".preChapter"],
    "vip_markers": ["chapter_vip", "VIP章节", "订阅本章", "购买本章", "余额不足"]
  }
}
```

关键实测发现：

1. **`browser_wait_selector` 三处都要配**（书籍页/目录页/章节页要等的元素不同）：
   原本只有顶层 `browser.wait_selector`，对 17K 这种「书籍页 + 独立目录页 + 章节页」
   三形态站点不够 —— 加了 `catalog.browser_wait_selector` 与
   `chapter.browser_wait_selector`。**不配就只能等固定毫秒，容易时快时慢地取到空 DOM**
   （实测：目录页只等 1.5s → **0 章**；页面其实要 3-5s 才渲染出 586 章）。
2. **`content_selector` 有变体**：同一站在不同请求下可能给
   `id="readAreaBox"` 或 `class="readAreaBox content"`。用 `content_selectors`
   候选列表更稳（按序取第一个命中）。
3. **VIP 信号在 CSS 文件名里**：免费章加载 `chapter_free.css`，付费章应为
   `chapter_vip.css` —— **正文里根本没有这个字样**，所以要用
   `chapter.vip_markers` + 在**整页 HTML** 上匹配（本项目新增
   `freeguard.check_page_markers`）。
   注意：这条规则只在一本**全免费**的 17K 书上实测过，`chapter_vip` 是按 CSS 命名
   规律推断的 —— 已如实记在规则 notes 里，并由第 4 层正文付费墙兜底。

### H. 反检测浏览器 + JSON 接口目录 + 卷→章展平（qidian.com）

**最难的一条**：腾讯云 Chaos VM（`__TENCENT_CHAOS_VM`，95KB 虚拟机式 JS 挑战）——
无头浏览器直接挡死。需**反检测浏览器**过挑战 + **JSON 接口**取目录 + **`flatten_field`** 展平卷→章。

```json
{
  "id": "qidian.com", "free_only": true, "fetch_mode": "browser", "requires_js": true,
  "match": ["qidian.com"],
  "book": {"url_pattern": "/book/(\\d+)/?", "title": [".book-info h1 em", "@title"]},
  "browser": {"anti_detect": true, "wait_selector": "#bookName", "wait_ms": 3500},
  "catalog": {
    "mode": "json_api",
    "json": {
      "url": "{origin}/ajax/book/category?bookId={bid}&_csrfToken={cookie:_csrfToken}",
      "items_path": "data.vs", "flatten_field": "cs",
      "cid_field": "id", "title_field": "cN",
      "vip_field": "sS", "vip_truthy": ["0"]
    },
    "url_template": "{origin}/chapter/{bid}/{cid}/",
    "sort": "document_order", "dedupe": "keep_first"
  },
  "chapter": {
    "content_selector": "main.content",
    "paragraph_selector": "span.content-text",
    "browser_wait_selector": "main.content span.content-text",
    "strip_selectors": ["span.review", ".review-count", ".chapter-nav", "aside"]
  }
}
```

关键实测发现：

1. **`sS` 字段反直觉：`1 = 免费`、`0 = VIP`**。实测 sS=1 的第 1 章 69 段 / 2408 字完整；
   sS=0 的章只有试读片段且命中「VIP章节」。故 `vip_truthy = ["0"]`。**别按直觉写成 ["1"]**。
2. **`{cookie:NAME}` 占位符**：起点 ajax 要求把 CSRF token 作为**查询参数**，
   光有 cookie 会被回 `{"code":1,"msg":"失败"}`。占位符从**当前页同源** `document.cookie`
   取值填入（先导航到书籍页，再在**页面内** `fetch()`——注意不能用 `page.goto` 直接开 JSON，
   那会被包进 `<pre>`）。
3. **`flatten_field`**：目录是 `data.vs[].cs[]`（卷 → 章）两层，`flatten_field="cs"`
   把它展平成扁平章节列表。
4. **`paragraph_selector`**：正文形如
   `<p><span class="content-text">痛！</span><span class="review">999</span></p>`，
   整块取文本会得到「痛！999」（段评数被混入）。按 `span.content-text` 逐段取即可。
5. **反检测是必需的**（见「浏览器路由」一节的「反检测模式」）：捆绑 Chromium + headless
   的 `sec-ch-ua` 含 `HeadlessChrome`、`navigator.webdriver=true` → 202 挑战页 42s 不放行；
   本机真 Chrome + headed + 关 AutomationControlled → 数秒出 67~70 万字节书页。
6. **等待条件不能塞宽松分支**（v0.5.1 修正）：`browser_wait_selector` 原为
   `"main.content span.content-text, #reader-content p"`，而 `#reader-content p` 在**骨架期就命中**
   → 等待**提前放行**，返回时 `span.content-text` 数 = **0**，全靠 `wait_ms` 兜。
   现收紧为只留 `main.content span.content-text`。详见「浏览器路由」一节的坑列表。

> 《诡秘之主》实测：1418 章 = **153 免费 + 1265 VIP**，VIP 章在目录接口层被判为 locked、
> **零请求**；抓 17 章 56 932 字，校对 PASS。

### I. 容器式目录项 + 子元素 VIP 标记（shuhai.com，杰奇 CMS）

**正版·含 VIP**，GBK 编码的**老式服务端渲染**站（杰奇 CMS：接口带 `ajax_gets=jieqi_contents`）。
目录由 `?method=getcatalog` 下发——**不带 `CALLBACK` 时直接返回裸 HTML**，
所以既不用 JSONP 解包、也不用浏览器路由。

```json
{
  "id": "shuhai.com", "free_only": true, "predecode": false,
  "match": ["shuhai.com"],
  "book": {
    "url_pattern": "/book/(\\d+)",
    "info_url": "{origin}/book/{bid}.htm",
    "title": ["@title"], "title_pattern": "^\\s*([^-]+?)\\s*-",
    "author": [".book-info-bookname"], "author_pattern": "作者[:：]\\s*(.+?)\\s*$",
    "intro": [".book-info-bookintro"]
  },
  "catalog": {
    "pages": {"mode": "single",
              "url": "{origin}/book/{bid}.htm?viptype=&method=getcatalog&ajax_request=1&ajax_gets=jieqi_contents"},
    "item_selector": "div.chapter-item",
    "vip_child_selector": "span.vip",
    "id_from": {"mode": "href", "pattern": "/read/(?P<b>\\d+)/(?P<cid>\\d+)\\.html"},
    "url_template": "{origin}/read/{bid}/{cid}.html",
    "sort": "cid_numeric_asc"
  },
  "chapter": {
    "title_selector": ".chapter-name",
    "content_selector": "#reader-content .chapter-item",
    "strip_selectors": [".chapter-name", ".chaper-info", "script", "style"]
  }
}
```

关键实测发现：

1. **详情页必须带 `.htm`**：`/book/{bid}.htm` 才是书籍页；`/book/{bid}`（不带）是另一张
   榜单页——实测 101449 不带 `.htm` 时页面上 48 个 `.book-name` 全是推荐位，
   真正的主书名一个都没有。
2. **章节项是容器，且 `<a>` 文本有 33% 是空的**：
   `<div class="chapter-item"><a href="/read/101449/3.html"></a> 第3章 初试神农十三针 </a>`
   ——标题落在 `</a>` **之后**（站点标记错位）。所以 `item_selector` 必须选**容器**、
   标题取容器文本；只选 `a` 会丢掉 215/645 个标题。
3. **VIP 标记是项内兄弟 span**：`<a …>第41章…</a><span class="vip"></span>`。
   它既不在 `<a>` 的 class、也不在父级 class 上 → 需要 `vip_child_selector`。
   ⚠ 判定范围**不能取「项自身的父级」**（那是整个目录容器，会匹配到别的条的 vip span，
   实测导致 645 章**全被判 protected**）。
4. **正文容器是 `#reader-content .chapter-item`**，不是 `.reader-content`
   （后者是导航条，只有 12 字；同页 `.chapter-item` 出现两次，第 2 个是「下一章」导航）。
5. **GBK**：站点 `Content-Type: charset=gbk`，本项目 http 层按响应头解码，无需特殊处理。

> 《神农医婿》实测：645 章 = **40 免费 + 605 VIP**（与目录里 `span.vip` 出现次数一致），
> VIP 章在目录层即判 locked、**零请求**；5 章 11 585 字，校对 + 产物终检 PASS。

### J. 正文来自 JSON 接口（tadu.com）

**正版·免费阅读 + 打赏（塔豆）**。目录 2416 章；**章节页是空壳**——
`<div id="artContent"></div>` 是空的，正文由 `read300-*.js` 调接口后写入 `.read_details`。
移动版 `m.tadu.com` 同样没有正文。

```json
{
  "id": "tadu.com", "free_only": true, "predecode": false,
  "match": ["tadu.com"],
  "book": {"url_pattern": "/book/(\\d+)", "info_url": "{origin}/book/{bid}",
           "title": ["meta[property='og:novel:book_name']"]},
  "catalog": {
    "pages": {"mode": "single", "url": "{origin}/book/catalogue/{bid}"},
    "item_selector": "div.chapter a[href*='/book/']",
    "id_from": {"mode": "href", "pattern": "/book/(?P<b>\\d+)/(?P<cid>\\d{6,})/?"},
    "url_template": "{origin}/book/{bid}/{cid}/",
    "sort": "document_order",
    "volume_selector": "h2", "vip_volume_markers": ["VIP", "付费"]
  },
  "chapter": {
    "content_selector": "div.nd-api-body",
    "paragraph_selector": "p",
    "body_api": {
      "url": "{origin}/getPartContentByCodeTable/{bid}/{seq}",
      "content_field": "data.content",
      "drop": {"selector": "p[data-limit]", "attr": "data-limit",
               "equals_base64_of": "cid"}
    }
  }
}
```

关键实测发现：

1. **`{seq}` 是章节序号，不是 cid**：接口是 `/getPartContentByCodeTable/{bid}/{seq}`，
   第 1 章 seq=1、cid=100812587。**排序必须用 `document_order`**，
   否则 `chapter.index` 与站点 seq 错位、全部取错正文。
2. **每个 `<p>` 都带 `data-limit`，其中若干段是站点水印**：`data-limit` 的值是
   `base64(…)`；**恰有若干段等于 `base64(当前章 cid)`**——那些不是正文，而是站点注入的
   **推广水印**（如「塔读小~。>说—*.—免费无广>告无*>弹窗，…」，夹杂随机噪声字符），
   且站点自己在浏览器里用 CSS（`.read_details p[data-limit="{encipher(cid)}"]{display:none}`）
   把它们藏起来。实测第 1 章：77 段里 **7 段是水印**，可见正文 1532 字 / 全文 1690 字。
   → `drop.equals_base64_of: "cid"` 精确剔除。
   **这不是绕过访问控制**：被隐藏的是站点自己的推广水印，不是正文；
   访客实际能读到的（70 段 / 1532 字）才是我们采集的范围。
3. **别把 `body_api` 片段追加在文档末尾**：解析器优先用 lxml，而 **lxml 会丢弃
   `</html>` 之后的内容**——片段会整块消失（症状：容器选不到，或选到了却为空）。
   引擎已改为插到 `</body>` 之前，自建实现时注意这点。
4. **目录里混有坏链接 `/book/{bid}/1/`**（访问返回「500 该章节不存在」）：
   同 cid 去重消不掉（cid 不同），故 item_selector 限定在 `div.chapter` 内、
   pattern 要求 cid 至少 6 位。
5. ⚠ **同章高频重复直连会被降级**：站点会把越来越多段落标记成「本次隐藏」→ 抽取结果变短。
   真人浏览器稳定（始终 7 隐藏 / 70 可见）。→ **每章只取一次**，别用 `--force` 反复重抓。

> 《仙妻如云》实测：2416 章全免费；3 章 5501 字，校对 + 产物终检 PASS。

### K. SSR 数据块即目录 + 章节页即入口（ciyuanji.com，Next.js）

**正版·含 VIP**。该站**没有书籍页**——`/book/{id}`、`/book/{id}.html`、`/novel/{id}`、
`/bookdetail/{id}` 等 9 种形态**全 404**，DOM 里也 0 个书籍页链接。
入口只能是**章节页** `/chapter/{bid}_{cid}.html`，而它自带全部需要的东西：
Next.js 把数据序列化进 `<script id="__NEXT_DATA__">`，里面有
`props.pageProps.bookChapter.chapterList`（673 章 + 逐章 `isFee`）
与 `props.pageProps.bookChapter.authorName`。

```json
{
  "id": "ciyuanji.com", "free_only": true, "fetch_mode": "browser",
  "match": ["ciyuanji.com"],
  "book": {
    "url_pattern": "/chapter/(\\d+)_\\d+",
    "info_url": "{url}",
    "title": ["@title"], "title_pattern": "^\\s*([^-]+)",
    "author": ["@json:props.pageProps.bookChapter.authorName"]
  },
  "catalog": {
    "mode": "json_api",
    "json": {
      "url": "{url}",
      "json_source": "script#__NEXT_DATA__",
      "items_path": "props.pageProps.bookChapter.chapterList",
      "cid_field": "chapterId", "title_field": "chapterName",
      "vip_field": "isFee", "vip_truthy": ["1"]
    },
    "url_template": "{origin}/chapter/{bid}_{cid}.html",
    "sort": "document_order"
  },
  "chapter": {
    "title_selector": "h1",
    "content_selector": "article[class^='chapter_article__']",
    "paragraph_selector": "p"
  },
  "browser": {"anti_detect": true}
}
```

关键点：

1. **`url`/`info_url` 用 `{url}`**（即用户给的那个 URL）：我们的 `catalog.pages.mode=single`
   在没有 `pages.url` 时就用来源页、`info_url` 默认也是 `{url}` —— 所以「没有书籍页」
   这类站不需要新机制，把入口定在章节页即可。
2. **`json_source`**：JSON 嵌在 HTML 里时先取出来再按 `items_path` 走（v0.7.0 新增）。
3. **`@json:<path>`** 取作者：作者只在数据块里，页面上没有稳定选择器（v0.7.0 新增）。
4. **`content_selector` 用属性前缀**：`article.chapter_article__vWEkb` 是 CSS-Modules 的
   **哈希类名**，重新构建就会变 → 写 `article[class^='chapter_article__']` 抗漂移。
   ⚠ 别用外层 `section.chapter_main__*`（含侧栏，中文量 10103 vs 正文 2046）。
5. ⚠ **正文是服务端加密的**：纯 HTTP 拿到的 `chapterContent.content` 是 base64 密文
   （中文 0 字），页面用前端 JS 解密。所以必须 `fetch_mode: browser`。
   **口径**：不属于「破解加密」——没有逆向密钥/算法，只是用真浏览器渲染页面、
   读站点对**所有访客**展示的内容（无登录、无验证码）。

> 实测《大唐：我真没想当神仙》：673 章 = **26 免费 + 647 VIP**（`isFee`），
> VIP 章零请求；3 章 10370 字，校对 + 产物终检 PASS。

### L. 免费/VIP 按**分段**判定 + 2 MB 目录页（faloo.com）

**正版·含 VIP**，**纯 HTTP**（服务端渲染）。书籍页 `/{bid}.html` 一次给出**全部章节**
（实测 12188 章，页面约 **2 MB**）；章节 URL 是 `/{bid}_{cid}.html`（**协议相对**写法 `//b.faloo.com/…`）。

```json
{
  "id": "faloo.com", "free_only": true,
  "match": ["faloo.com"],
  "book": {
    "url_pattern": "/(\\d{6,})(?:_\\d+)?\\.html",
    "info_url": "{origin}/{bid}.html",
    "title": ["@title"], "title_pattern": "^\\s*([^_]+)",
    "author": ["@title"], "author_pattern": "^[^_]+_([^_]+?)(?:小说|著)"
  },
  "catalog": {
    "pages": {"mode": "single", "url": "{origin}/{bid}.html"},
    "item_selector": "#mulu div.DivTr a",
    "volume_selector": "div.DivVip",
    "vip_volume_markers": ["VIP"],
    "id_from": {"mode": "href", "pattern": "/(?P<b>\\d+)_(?P<cid>\\d+)\\.html"},
    "url_template": "{origin}/{bid}_{cid}.html",
    "sort": "cid_numeric_asc"
  },
  "chapter": {
    "title_selector": "h1",
    "content_selector": "div.noveContent",
    "paragraph_selector": "p",
    "drop_leading_title_paragraph": true
  }
}
```

关键点：

1. **免费/VIP 的分界在「分段」上，不在逐章标记上**：`#mulu` 的直接子元素依次是
   `div.TitleDiv` → `div.C-Fo-Z-ML-TitleBox` → `div.DivTable`（**免费**，49 章，单元格 `DivTd3`）
   → **`div.DivVip`**（文本含「VIP章节部分」）→ `div.DivTable`（**VIP**，12139 章，单元格 `DivTd`）。
   逐章**没有任何 VIP class/图标**（实测目录内 vip 图标数 = 0）
   → `volume_selector: "div.DivVip"` + `vip_volume_markers: ["VIP"]`（v0.6.0 的能力）。
2. **`item_selector` 要用行容器**：`#mulu div.DivTr a`。别用 `#mulu a[href]`
   （会把「VIP充值 / VIP用户单章订阅」等功能链接也吃进来），也别用 `div.DivTd3 a`
   （只取免费表，丢掉「12139 章被拦下」的会计）。
3. **首段就是标题行**且无 class 可剔 → `drop_leading_title_paragraph: true`
   （v0.7.0 新增；仅当首段与目录标题**完全相同**时才删）。
4. ⚠ **2 MB 页面踩到 lxml 的静默截断**：见下方「大页面/畸形 HTML」告警。

> 实测《洪荒：推演神话法，打造至高洪荒》：12188 章 = **49 免费 + 12139 VIP**，
> VIP 零请求；3 章 6087 字，校对 + 产物终检 PASS。

> ⚠ **大页面 / 畸形 HTML 必读**：`make_soup` 优先 lxml，但 **lxml 会静默丢内容**。
> 实测飞卢这张 2 MB 页面：原文 `<a>` 12356 个、章节 12188 个，lxml 只解析出 3128 个 `<a>`、
> 3058 章，**且不报错**。本仓已加 `_parse_looks_complete()` 完整性校验（比对原文与树里
> `<a>/<div>/<p>` 数量，明显不符就退回 `html.parser`）。自己写解析器时务必做同样的校验。

### M. 免费镜像族 + 等待条件**按角色**声明（shudugu.org）

速读谷这类镜像站的形态很标准，价值主要在**两个坑**上（都是 v0.8.1 实测踩到的）：

```json
{
  "fetch_mode": "browser",
  "match": ["shudugu.org", "sudugu.cc"],
  "book": {
    "url_pattern": "/(\\d+)/",
    "info_url": "{origin}/{bid}/",
    "title": ["@title"],
    "title_pattern": "^\\s*([^-]+)",
    "author": ["@title"],
    "author_pattern": "^(?:[^-]+-){3}\\s*([^-]+)"
  },
  "catalog": {
    "pages": {"mode": "single", "url": "{origin}/{bid}/"},
    "item_selector": "#list a[href$='.html'], div.dir a[href$='.html']",
    "id_from": {"mode": "href", "pattern": "/(?P<cid>\\d+)\\.html"},
    "url_template": "{origin}/{bid}/{cid}.html",
    "sort": "cid_numeric_asc",
    "dedupe": "keep_first"
  },
  "chapter": {"title_selector": "h1", "content_selector": "div.con"},
  "browser": {
    "anti_detect": true,
    "wait_selector": {"chapter": "div.con"},
    "wait_ms": 1500
  }
}
```

**坑 1：书名不能用 `h1`。** 该站书页 `h1` 是「**653.5万字 捞尸人**」——字数前缀被当成书名一部分。
书名/作者统一走 `<title>` 分段正则（`捞尸人-完本小说全文阅读-…-纯洁滴小龙-速读谷`：
第 1 段书名、第 4 段作者）。

**坑 2：等待条件必须按角色声明。** 目录是**新章在前**（相邻 cid 递减：4419510 → 4419509 → 4419499），
所以 `sort` 要用 `cid_numeric_asc` 而非 `document_order`。但更隐蔽的是等待条件：
把章节容器 `div.con` 写成**顶层字符串**后，顶层是**全角色广播** →
**书籍页**也去等 `div.con`（那里根本没有）→ 白等满 30 秒超时才继续。
目录耗时 **37.0s → 7.6s**（改对象写法后）。所以：

```json
"wait_selector": {"chapter": "div.con"}     // ✅ 只作用于章节页
"wait_selector": "div.con"                  // ❌ 书籍页/目录页一起遭殃
```

> 实测《捞尸人》：目录 **790 章**（原始 794 链接，去重后 790）、正文 `div.con` 1815 汉字；
> 抓 6 章 14957 字，导出 TXT/MD/EPUB/HTML 四格式，校对 **PASS**。

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
  ⚠ 钳制看的是**正文的实际路由**（`chapter.fetch_mode`），不是顶层值 —— 见下节。
- **不参与任何凭据环节**：不注入 Cookie、不登录、不接管你的浏览器会话。
  若站点要求完成人机验证（captcha），本路由同样会失败——那是需要人参与的步骤，
  代码里不做绕过。
- **每个导航用独立页面**（实测踩过）：Nuxt/Next 这类 SPA 在文档加载后会立即做客户端
  路由，复用同一个 page 连续 `goto` 会互相中断 → `net::ERR_ABORTED` 且内容为空
  （七猫 20 章全 failed）。改为每次 `new_page()`（同 context，WAF cookie 保留）。
- **不能进线程池**（实测踩过）：Playwright 同步对象绑定创建它的线程，
  `ThreadPoolExecutor` 会新建线程 → `Cannot switch to a different thread`。
  browser 模式必须主线程顺序抓。
- **`net::ERR_ABORTED` 要容错**：SPA 场景下先捕获再等目标元素，
  配合 `browser_wait_selector` 比死等固定毫秒更稳。
- **瞬时网络错误要重试，且必须带退避**（v0.8.1）。免费镜像站「抽风」不是单次抖动，
  而是**一段时间内持续 reset/timeout**（同一 URL 时而 200 时而 `ERR_CONNECTION_RESET`）。
  实测速读谷：0 退避连发 3 次重试 → **三次全 reset**；加 `1.2s × n` 退避后
  **首个重试即成功**。故重试次数由 `browser.nav_retries`（1~8，默认 4）控制，
  间隔按 `1.2s × 第几次` 递增。⚠ 只对**瞬时**错误重试（`ERR_CONNECTION_RESET` /
  `ERR_TIMED_OUT` / `ERR_EMPTY_RESPONSE` 等）；`ERR_ABORTED` 是 SPA 客户端路由中断，
  **不是错误**，不重试。
- **等待条件按角色声明**（v0.8.1）：`browser.wait_selector` 支持对象写法
  `{"book": …, "catalog": …, "chapter": …}`；字符串写法是全角色广播，
  把章节容器写成字符串会让书籍页白等超时（见案例 M）。
- **先试 HTTP 再上浏览器**：实测有反直觉的情况——纵横的 `showchapter` 页用无头浏览器
  打开只看到 2 个章节链接（JS 版是懒加载的），而**纯 HTTP 取到的静态 HTML 里有完整
  700 章**。所以不要默认"JS 站就得用浏览器"，先用 `probe_site.py` 与
  `python -m noveldown probe` 各试一次，用实测证据决定。
- **拆除耗时可能比抓取本身还大**（v0.8.13，本机实测）：Playwright 的优雅拆除在这台机器上
  `browser.close()` **47.8~50.4s**、`pw.stop()` **33.6~36.0s**，而一次浏览器抓取的真实
  工作量常常只有几秒 —— 豆瓣专栏 3 章总 **61.9s**，其中 **58.5s** 是拆除。
  现改为「**先杀本实例的进程树，再 `pw.stop()`**」：实测 **0.00s + 0.04s**，
  残留子进程 **0**（总耗时 → **13.3s**）。
  · 需要 `psutil`（软依赖，没装自动退回优雅拆除，只是慢）。
  · 只杀**本进程的后代**且 cmdline 命中本实例特征（专属临时 profile / `run-driver`），
    **不会碰你自己开的浏览器**；可用 `NOVELDOWN_NO_FAST_CLOSE=1` 关掉。
- ⚠ **`wait_selector` 是 OR 语义，别塞宽松分支**（v0.5.1 实测踩到）：
  `wait_for_selector("A, B")` **任一分支命中就返回**。若其中一支在**骨架期**就存在，
  等待会**提前放行**，随后取到的 DOM 里正文是空的。
  实测起点：`"main.content span.content-text, #reader-content p"` 中
  `#reader-content p` 骨架期即命中 → 返回时 `span.content-text` 数 = **0**（`main.content p` = 69），
  该等待**完全没起作用**，只是被 `wait_ms` 掩盖了。
  对照实验（同页、`wait_ms=0`）：只留 `main.content span.content-text` → **69 段**、首段「痛！」；
  旧 OR → **0 段**。
  → **只放"真正代表内容就绪"的那一支**；宁可等超时（引擎会警告并继续），也不要在骨架上放行。
  变体兼容交给**抽取阶段**的候选列表（`content_selectors` / `paragraph_selector` 回退）。

### 分段路由（`book`/`catalog`/`chapter` 各自的 `fetch_mode`）

三处页面的形态**天然不同**，顶层一个 `fetch_mode` 经常只能二选一。
段内覆盖让每一段各走各的路由：

```json
{
  "fetch_mode": "browser",
  "browser": { "wait_selector": {"chapter": "div.read-con"} },
  "chapter": { "fetch_mode": "http", "content_selector": "div.art_con" }
}
```

解析规则：**段内 > 顶层**；未声明的角色继承顶层；非法值（不是 `http`/`browser`）
**加载即报错**，不留到抓取那一刻才炸。

**书山（shushan.zhangyue.net）的教训**（v0.8.13）：
一开始判定它「目录靠 JS 渲染」→ 顶层 `browser`，实测 3 章 **82.6 秒**，
而且**只拿到 1 章**。复测后真相是：

| 页面 | 真相 | 手段 |
|---|---|---|
| 书籍页 `/book/{bid}/` | 静态 HTML 里**只有 1 个** `/book/` 链接 | 目录不在这里 |
| 目录 | 点 `#directory` 后发出的 **XHR 片段** `/book/directory?bid=` | 纯 HTTP **0.5s** → 821 条 cid，与页面「目录（821章）」吻合 |
| 章节页 `/book/{bid}/{cid}` | 服务端直出，`div.art_con` | 纯 HTTP **0.2s** / 3240 字 |
| 简介 | 书籍页里**没有**；`meta[name=description]` 是站点通用文案 | `book.info_api` → `/book/bookintro?bid=` |

改完后：**全 HTTP**（`fetch_mode: http`）、821 章全部可枚举、
`--limit 30 --concurrency 4` 用 **23.2 秒**（0.77s/章）、校对 PASS。

> **可复用的判据**：看到「点了某个元素才出现的内容」，先**别急着上 `click_selectors`** ——
> 用 `tools/hunt_api.py` 监听一次网络，看点击到底触发了哪个 XHR。
> 能直取的片段接口，比让浏览器点一下稳定得多，也把并发还给了正文。

⚠ **另一个坑**：DOM 采样时机。同一份页面在点击后 400ms 有 822 条链接、2s 后塌成 16 条
（虚拟滚动/二次渲染），`wait_ms` 填大了反而读到**塌缩后**的 DOM。
判断「目录到底有多少章」时，用**页面上写的章数**（「目录（821章）」）交叉验证，
不要只信某一时刻的 DOM 计数。

### 反检测模式（`browser.anti_detect`）—— 过 WAF/机器人挑战

有些站点的 WAF 会**识别自动化浏览器**本身（不只识别请求特征）。此时打开：

```json
{
  "fetch_mode": "browser",
  "browser": {
    "anti_detect": true,
    "wait_selector": "#bookName",
    "wait_ms": 3500
  }
}
```

反检测模式做的三件事（缺一不可，见 `noveldown/browser.py`）：

| 项 | 为什么 |
|---|---|
| `channel="chrome"` | 用本机**真** Chrome，而非 playwright 捆绑 Chromium |
| `headless=False`（**headed**） | 捆绑 Chromium + headless 会在请求头 `sec-ch-ua` 里明写 `HeadlessChrome` —— 一行就被识破 |
| `--disable-blink-features=AutomationControlled` 等 | 关掉「受自动化控制」等自动化特征 |

另外注入 `CONSISTENCY_JS`：把 `navigator.languages` 对齐到 `zh-CN,zh`
（否则 `locale="zh-CN"` 与默认的 `en-US,en` 自相矛盾，反爬常查这个自洽性）。

实测（起点，2026-09-20）：捆绑 Chromium + headless 在腾讯云 Chaos VM 的 202 挑战页
**42s 不放行**；反检测模式**数秒**渲染出 **67~70 万字节**书页，
指纹 `navigator.webdriver=false`、`plugins=5`、`languages=zh-CN,zh`、UA 不含 `HeadlessChrome`。

要点：

- **需要本机装有 Google Chrome**。没装会明确报错并提示关掉 `anti_detect`。
- **必须有桌面会话**（headed）。纯服务器无显示器时不适合此模式。
- **可选增强**：如需更强的指纹伪装，可自备 puppeteer-extra 的 `stealth.min.js`
  并用 `NOVELDOWN_STEALTH_JS`（或规则 `browser.stealth_js`）指定路径。
  **本项目不随仓分发该脚本**——实测对起点非必需（A/B 对照结果一致），
  且本仓铁律「第三方源码不入仓」。详见 [REFERENCE.md](./REFERENCE.md) 第六节。
- **仍然不做凭据环节**：不登录、不接管会话、不绕过人机验证。

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

### 途径一（优先）：按 glyph 名字解码 —— 秒级，**不需要参考字体**

这是字体反爬里**最常见也最便宜**的做法。子集字体不给 PUA 真实 cmap，
但 glyph 名保留了可读信息。两种主流写法：

| 写法 | 例子 | 解法 |
|---|---|---|
| **英文单词** | `zero` / `one` / … / `nine` / `period` | 查单词表 → `0123456789.` |
| **码位十六进制** | `uni98CE` / `u5929` / `CJK UNIFIED IDEOGRAPH-98CE` | 直接 `chr(int(hex, 16))` |
| 单字符名 | `A` / `5` / `zero.sc`（去 `.后缀`） | 直接取该字符 |
| **索引名**（解不出） | `gid58646` / `cid44285` | **明确放弃** —— 那是索引不是字符 |

> 这条路子源自起点老版反爬（见 [REFERENCE.md](./REFERENCE.md) 中知乎 58209887 的记账）：
> 数字被映射成乱码，但 `TTFont.getBestCmap()` 拿到的 glyph 名就是英文单词，直接可还原。

`fontdecode.char_from_glyph_name()` 实现这套解析；`map_from_glyph_names()` 给出覆盖率。
**覆盖率 ≥ 60% 就走这条路**，否则自动退回途径二。

### 途径二（兜底）：字形轮廓匹配 —— 用**随仓索引**，零下载

子集字体的 CFF charstring 就是来源字体的**字形轮廓**。把每个字形的轮廓点集序列化取哈希，
即可与同版本参考字体的字形**精确对应**（不是 OCR 近似）：

```python
from fontTools.pens.recordingPen import RecordingPen
pen = RecordingPen(); glyph_set[name].draw(pen)
key = ";".join(op + "|" + ",".join(f"{x:g}/{y:g}" for x, y in pts)
               for op, pts in pen.value)   # → sha1(key)
```

**只在途径一解不出时才需要它**（例如番茄用 `gid58646` 这类索引名）。
索引**随仓库分发**（`noveldown/fontmaps/sourcehan-sc-2.002.bin`，44 260 条，459 KB），
所以运行时**不联网、不下载 17 MB 参考字体**。
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
:: 什么都不用做 —— 轮廓索引已随仓库分发，运行时零下载
python -m noveldown probe "https://fanqienovel.com/page/<bookId>"

:: （仅维护者）从 OFL-1.1 参考字体重建随仓索引，需联网下载约 17MB
python tools\build_fontmap.py --shipped --force

:: 校验随仓索引可读、条目数正常
python tools\build_fontmap.py --verify
```

依赖：`fontTools`（+ `brotli`，读 woff2 时需要）。**只影响这类站点**，
缺失时其它站点照常工作，并会给出带 pip 命令的明确提示。

> 参考字体**本体（16MB）不随仓库分发**，但**派生索引随仓**（459KB）——这是
> v0.5.0 起的改动：让终端用户开箱即用、完全离线。索引由 `tools/build_fontmap.py`
> 离线从 OFL-1.1 的 SourceHanSansSC-Normal 2.002 派生。理由与许可依据见
> [REFERENCE.md](./REFERENCE.md) 第四节。

---

## 调试技巧

```bat
:: 看规则是否加载、字段取值
python -m noveldown rules

:: 单站规则自检（抓目录 + 抽 1 章，打印每一环的命中数）
python -m noveldown probe "URL"

:: 未知站点的原始结构（select / 链接形状 / 正文容器候选 / base64 命中）
python tools\probe_site.py "URL"
```

离线回归测试：

```bat
python -m unittest discover -s tests -t .
```

新增规则后建议把该站的**目录页与章节页各存一份**到 `tests/fixtures/`，
并按 `tests/test_parser.py` 的样式补一个回归用例——站点改版时能立刻发现。
