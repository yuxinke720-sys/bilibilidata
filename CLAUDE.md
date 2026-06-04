# Bilibili《每周必看》数据分析 — Claude 指南

大数据课程小组课题。对 B 站《每周必看》栏目收录的视频与 UP 主数据做
采集→清洗→HDFS→Spark SQL→Spark MLlib→Pyecharts 可视化的完整流水线，
并产出《课题报告书》打包提交。

---

## 🖥️ 运行环境硬约束（必读，决定全部代码写法）

| 角色 | 机器 | 系统 / 架构 |
|------|------|-------------|
| **开发机** | 本人 Mac | macOS, Apple Silicon **M4 / ARM64** |
| **交付/评测机** | 老师提供的虚拟机 | **Ubuntu 22.04.2 LTS / amd64** |

**核心事实：开发在 Mac，最终要能搬到 Ubuntu 22.04 VM 上跑。** 两者同为类 Unix，
Spark/Hadoop/Python 行为一致，可移植性天然很好。ARM 与 amd64 的差异对纯 Python +
JVM（Spark/Hadoop 跑在 JVM 上）**没有影响**——不要为 CPU 架构做任何特殊处理。

老师给出的**标准实验配置环境**（写进报告"项目实践环境"一节，须严格对齐）：

| 类别 | 配置 | 版本号 |
|------|------|--------|
| 操作系统 | Ubuntu | 22.04.2 LTS amd64 |
| 编程语言 | Python | 3.8.16（注：VM 里实际默认是 3.8.10，小版本差异不影响核心逻辑） |
| 大数据存储 | Hadoop | 3.1.3 |
| 大数据计算 | Spark | 3.2.0 |
| 环境管理 | Anaconda | 4.10.1 |
| IDE | **PyCharm**（报告书要求用 PyCharm + Python 实现）；VM 里也装了 VS Code | — |

其他依赖：jieba / pandas / pyecharts / requests / faker / brotli / retry。

**最终必须在老师的标准环境（Ubuntu 22.04 + 上述版本）里跑通一次。** 开发可先在
Mac 上做，但提交前要在 Ubuntu 上验证。本地验证用 VMware Fusion（个人免费）或 UTM
装 Ubuntu 22.04 ARM64 即可——架构差异对纯 Python + JVM 代码无影响。

### ⚠️ 可移植性铁律（搬到 Ubuntu 必然踩、必须提前规避的坑）

1. **只用相对路径，禁止任何绝对路径。**
   所有读写以项目根为基准：`./data`、`./output`、`./static`。
   严禁出现 `/Users/yxk/...`、`/home/xxx/...`、`~`、`C:\...`。
   脚本里需要时用 `os.path.join` 拼相对路径，不要手写斜杠。

2. **文件编码统一 UTF-8、无 BOM。**
   每个 `open()` 都显式写 `encoding='utf-8'`；写 JSON 用 `ensure_ascii=False`。
   不写 `gbk`，不依赖系统默认编码（Mac 默认 utf-8，旧 Windows 是 gbk，会炸）。

3. **换行统一 LF（`\n`），不要 CRLF。**
   仓库已加 `.gitattributes` 强制 `* text eol=lf`。生成 txt 时不要用 `\r\n`。

4. **清洗输出 txt 的分隔符 = 制表符 `\t`，且写入前先把字段内的 `\t \n \r`
   及多余空白清掉。** 原因：标题/简介含中文逗号，CSV 逗号分隔会串列；
   先 sanitize 再用 `\t` 分隔，Spark 用 `sep='\t'` 读取最稳。
   （如某字段仍可能含 Tab，退而用 `` 作分隔符。）

5. **HDFS 地址不要写死。** 用顶部常量集中管理，便于换机器时一处修改：
   ```python
   HDFS_BASE = "hdfs://localhost:9000"     # Ubuntu VM 上按实际改这一行
   INPUT_TXT = "/user/hadoop/bilibili/bilibili_week.txt"
   ```
   本地无 HDFS 时，Spark 可临时用 `file://` 读本地 txt 做调试，规则同样集中常量。

6. **依赖可复现。** 新增第三方库必须同步写进 `requirements.txt`（带版本号），
   保证在 Ubuntu 上 `pip install -r requirements.txt` 能一键装齐。
   不引入只有 Mac 才有的库，不依赖 Homebrew 专属路径。

7. **不提交 Mac 垃圾文件。** `.DS_Store`、`__MACOSX`、`.idea/` 等已在 `.gitignore`，
   打包 zip 前确认没混进去。

8. **jieba 词典 / 停用词表用相对路径加载**（如 `./static/stopwords.txt`），
   并把停用词文件一并放进交付物，换机器不丢。

9. **Pyecharts 渲染的 HTML 资源可离线打开**：优先本地/内置 assets，避免只能联网看图。

> 一句话总结：**绝对路径、写死的 HDFS 地址、非 UTF-8 编码、CRLF 换行、逗号分隔**
> 是搬家五大杀手。代码里逐条规避，搬到 Ubuntu 基本原样能跑。

---

## 📦 交付物结构（最终打包必须严格照此，否则不合规）

截止：**2025-06-21 24:00**。最终压缩为 `第x组_项目报告.zip`：

```
第x组_项目报告.zip
└── 第x组_项目报告/
    ├── 课题报告书.pdf  (或 .doc)        ← 按 模板_课题报告书.docx 填写
    └── Source Code/
        ├── bilibili_week.py              ← 爬虫（PDF 固定名）
        ├── data_process.py               ← 数据清洗
        ├── data_analysize1.py            ← Spark SQL 分析
        ├── data_analysize2.py            ← Spark MLlib
        ├── echarts_show.py               ← 可视化
        ├── chineseStopWords.txt          ← 中文停用词
        ├── requirements.txt
        ├── static/                       ← 分析结果 csv
        ├── html/                         ← 可视化 html（含 index.html）
        └── Data/
            ├── week_*.json               ← 源数据（保持原文件名；过大可酌情删）
            └── bilibili_week.txt         ← 清洗后数据（保持原文件名）
```

规则：源数据 + 清洗后数据放 `Data/`；代码 + `Data/` 放 `Source Code/`；
`Source Code/` + 报告书放 `第x组_项目报告/`；最外层压缩成同名 zip。
**开发过程中文件命名要"见名知意"**（清洗后别再叫 `out.txt`）。

---

## 🧱 项目模块与流水线（文件名严格对齐 PDF 参考解法）

PDF 里的工程名为 `BigData`，**代码文件名是固定的，照抄**（"严格按照 PDF"）：

| 模块 | 脚本（PDF 固定名） | 职责 | 产出 |
|------|--------------------|------|------|
| 0 采集 | `bilibili_week.py` | 请求官方 API 抓每期 JSON，随机 UA / Cookie / retry | `./data/week_*.json` |
| 1 预处理 | `data_process.py` | 解析 JSON→Pandas，选字段/去空去重/去异常/补文本，合并去表头存 txt，上传 HDFS | `bilibili_week.txt` → HDFS |
| 2 Spark SQL | `data_analysize1.py` | Top10 UP/分区，各互动 Top10 视频与 UP，jieba 词频 Top300 | `./static/*.csv` |
| 3 MLlib | `data_analysize2.py` | `his_rank<=10→label=1`，8:2 切分，斯皮尔曼相关，LR/DT/RF/GBT，Acc+AUC | `./static/*.csv` |
| 4 可视化 | `echarts_show.py` | 柱状/饼/词云/相关性热力图/分类器双柱，`./html/index.html` 汇总跳转 | `./html/*.html` |

配套文件：`chineseStopWords.txt`（中文停用词，jieba 用，相对路径加载）、`requirements.txt`。

**开发期工程目录结构**（PDF 的 BigData 布局，提交时再按上面的 zip 结构重组）：
```
BigData/
├── data/                    爬虫 JSON（过大，提交时删除）
├── static/                  spark 分析结果 csv
├── html/                    可视化 html（index.html 汇总跳转）
├── bilibili_week.py
├── data_process.py
├── data_analysize1.py
├── data_analysize2.py
├── echarts_show.py
├── chineseStopWords.txt
├── bilibili_week.txt        清洗后数据（也上传 HDFS）
└── requirements.txt
```

**当前进度**：模块 0 已有脚本、`./data` 下已爬好 **304 期**（第 20~326 期），无需重爬。
注：PDF 截止 2023-05-19 用 217 期，我们数据更多，分析照常。`get_bilibili_week.py`
有小 bug：存储目录写成 `./dat`（应为 `./data`），只在重爬时影响。下一步从模块 1 开始。

---

## 📐 PDF 权威规格（建造蓝图，逐条照做）

### 模块 1 清洗规则（data_process.py）
逐个读 `./data/week_*.json`，`data` 下含 config / list：
- **选字段**：`期数=config.name`、`up=list[].owner.name`、`title`、`desc`、`rcmd_reason`、
  `tname`、以及 `stat` 里的 `view/danmaku/reply/favorite/coin/share/like/his_rank/dislike`。
- **去空 + 去重**：删含空值与重复行（**重复判定 = up 名与 title 同时相同**）。
- **去异常**：`view/danmaku/reply/favorite/coin/share/like/his_rank <= 0` 或 `dislike > 0`
  视为异常删除；之后 `dislike` 字段无意义，**删列**。
- **补文本**：`desc`、`rcmd_reason` 为空时用 `title` 填充；清掉换行符、Tab 等特殊符号。
- **合并**：所有 df 纵向合并，**去掉表头**，存为 `bilibili_week.txt`。
- **上传**：`./bin/hdfs dfs -put .../bilibili_week.txt /user/hadoop`。

**清洗后 txt 列顺序（须与模块 2 的 schema 严格一致）**，制表符 `\t` 分隔、UTF-8、LF：
```
1 period(期数)  2 up  3 title  4 tname  5 view  6 danmaku  7 reply
8 favorite  9 coin  10 share  11 like  12 his_rank  13 desc  14 rcmd_reason
```
（文本字段 desc/rcmd_reason 放最后，降低分隔符串列风险。）

### 模块 2 Spark SQL（data_analysize1.py）
HDFS textFile→RDD→map 切分→Row→定义 schema→DataFrame→注册临时视图 `data`：
- ① `count(up)` 分组降序，Top10 收录最多 UP → `popular_up.csv`
- ② `count(tname)` 分组降序，Top10 收录最多分区 → `popular_subject.csv`
- ③ 播放量：`title,view` 降序 Top10 视频；`up, sum(view)` 分组降序 Top10 UP → csv
- 同法对 `danmaku/reply/favorite/coin/share/like` 各出 Top10 视频 + Top10 UP
- ④ 词频：jieba `pretty_cut` 对 `title/desc/rcmd_reason` 分词去停用词，取 Top300 非空 → csv
- 结果均 `toPandas().to_csv()` 存 `./static/`

### 模块 3 Spark MLlib（data_analysize2.py）
- 选 `['view','danmaku','reply','favorite','coin','share','like']` 研究与 `his_rank` 关系。
- **标签**：`his_rank<=10 → label=1`（曾进热搜前十），否则 0。
- `VectorAssembler` 组特征向量 → 8:2 切训练/验证集。
- 斯皮尔曼相关：`pyspark.ml.stat.Correlation` → csv。
- 分类器：逻辑回归(maxIter=15) / 决策树 / 随机森林 / GBT 四种。
- 评估：`MulticlassClassificationEvaluator`(Accuracy) + `BinaryClassificationEvaluator`(AUC) → csv。

### 模块 4 可视化（echarts_show.py，pyecharts）
读 `./static/*.csv` 绘图，全部输出到 `./html/`：
- 各互动指标（view/coin/danmaku/favorite/like/reply/share）的视频 + UP 柱状图，`Page` 上下布局
- 收录次数：分区/UP 柱状图 + 富文本饼图，`Grid` 左右布局
- 词云：title/desc/rcmd_reason 三个 `WordCloud`，`Page` 布局
- 相关性热力图（`[i,j,value]` 列表）；分类器 Acc/AUC 双柱状图
- 末尾写 `./html/index.html`，超链接汇总各结果页跳转

### 报告"五、遇到的问题"现成素材（PDF 原文，可直接用）
1. pyspark 版本：conda 新建虚拟环境 `pip install pyspark==3.2.0`，实际用的是 pyspark 自带
   的 spark，与系统装的 spark 无关，更简便。
2. 爬虫在 Windows 下常报"未能连接/拒绝请求"，需反复跑；Linux 下稳定，故采集在 VM 里做。
3. B站数据实时更新，每次跑播放量/转发数都不同；报告结果为某截止日的快照，微小波动不影响整体结论。

### 参考资料（写进报告"六、参考内容"）
- B站爬虫参考：https://www.heywhale.com/mw/project/6059c0f0c910a9001581c98b
- Spark 数据分析案例（厦大林子雨）：https://dblab.xmu.edu.cn/blog/2738/
- pyecharts 文档：https://pyecharts.org/#/zh-cn/intro

---

## ✅ 写代码时的固定检查清单

- [ ] 没有绝对路径，全部 `./` 相对路径
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] 输出 txt：字段已清掉 `\t\n\r`，用 `\t` 分隔，LF 换行
- [ ] HDFS / 路径常量集中在脚本顶部，一处可改
- [ ] 新依赖已写进 `requirements.txt`
- [ ] 文件名见名知意，符合交付 zip 结构

---

## 🗣️ 对话约定（给 Claude）

**每次回复的最后一句，必须以这一行结尾**（一字不差，包含书名号）：

> 接下来要做什么 运河儿
