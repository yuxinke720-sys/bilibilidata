# -*- coding: utf-8 -*-
"""
echarts_show.py —— 模块4：pyecharts 可视化（严格按项目 PDF）

读 ./static/*.csv 绘图，全部输出到 ./html/，并生成 index.html 汇总跳转：
  ① 7 个互动指标(view/danmaku/reply/favorite/coin/share/like) 的
     Top10 视频 + Top10 UP 柱状图（Page 上下布局）   → <metric>.html
  ② 收录次数：分区柱状图 + 富文本饼图（Grid 左右布局） → subject.html
     收录次数：UP   柱状图 + 富文本饼图（Grid 左右布局） → up_count.html
  ③ title/desc/rcmd_reason 三词云（Page 布局）          → wordcloud.html
  ④ 斯皮尔曼相关性热力图                                → correlation.html
     四分类器 Accuracy/AUC 双柱状图                     → classifier.html
  ⑤ index.html 超链接汇总各结果页

可移植性（见 CLAUDE.md）：相对路径、UTF-8、离线 assets（本地 echarts JS）。
运行：  python echarts_show.py
"""
import os
import csv
import base64

from pyecharts import options as opts
from pyecharts.charts import Bar, Pie, WordCloud, HeatMap, Page, Grid
from pyecharts.globals import CurrentConfig

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
STATIC_DIR = "./static"
HTML_DIR = "./html"
ASSETS_DIR = os.path.join(HTML_DIR, "assets")

# 离线 assets：图表引用 ./assets 下本地 echarts JS（相对各 html 所在的 ./html/）
CurrentConfig.ONLINE_HOST = "./assets/"
CDN_HOST = "https://assets.pyecharts.org/assets/v5/"
ASSET_FILES = ["echarts.min.js", "echarts-wordcloud.min.js"]

# ---------------------------------------------------------------------------
# B 站风格背景：淡粉底 + 平铺的“小电视”图标 + “第六组作业”水印
# 小电视为自绘 SVG 几何图形（规避官方版权），水印很淡不挡图表
# ---------------------------------------------------------------------------
WATERMARK_GROUP = "第六组作业"
BILI_PINK = "#FB7299"
_WM_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">'
    '<g transform="rotate(-22 150 100)" opacity="0.10">'
    # 天线（细、圆头，向上外伸，贴近官方造型）
    '<path d="M86 70 L66 40" stroke="#FB7299" stroke-width="5" stroke-linecap="round" fill="none"/>'
    '<path d="M114 70 L134 40" stroke="#FB7299" stroke-width="5" stroke-linecap="round" fill="none"/>'
    '<circle cx="66" cy="40" r="4" fill="#FB7299"/>'
    '<circle cx="134" cy="40" r="4" fill="#FB7299"/>'
    # 机身（大圆角的圆角矩形）
    '<rect x="58" y="66" width="84" height="64" rx="22" fill="#FB7299"/>'
    # 眼睛（白色竖向胶囊）
    '<rect x="82" y="86" width="8" height="15" rx="4" fill="#ffffff"/>'
    '<rect x="110" y="86" width="8" height="15" rx="4" fill="#ffffff"/>'
    # 微笑
    '<path d="M90 110 Q100 118 110 110" stroke="#ffffff" stroke-width="3" '
    'stroke-linecap="round" fill="none"/>'
    # 水印文字
    '<text x="100" y="162" font-size="21" text-anchor="middle" fill="#FB7299" '
    'font-family="PingFang SC,Microsoft YaHei,sans-serif">' + WATERMARK_GROUP + '</text>'
    '</g></svg>'
)
_WM_B64 = base64.b64encode(_WM_SVG.encode("utf-8")).decode("ascii")
BG_STYLE = (
    "<style>"
    "body{background-color:#fff5f9;"
    "background-image:url('data:image/svg+xml;base64," + _WM_B64 + "');"
    "background-repeat:repeat;background-attachment:fixed;}"
    "</style>"
)


def inject_background(path):
    """把 B 站风格背景 + 水印样式注入已渲染的 html。"""
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    if "</head>" in html and "fff5f9" not in html:
        html = html.replace("</head>", BG_STYLE + "</head>", 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

# 互动指标 → 中文显示名
METRICS = [
    ("view", "播放量"), ("danmaku", "弹幕数"), ("reply", "评论数"),
    ("favorite", "收藏数"), ("coin", "投币数"), ("share", "分享数"), ("like", "点赞数"),
]
FEATURES = ["view", "danmaku", "reply", "favorite", "coin", "share", "like"]
FEATURES_CN = ["播放量", "弹幕数", "评论数", "收藏数", "投币数", "分享数", "点赞数"]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def read_csv(name):
    """读 ./static/<name>.csv，返回 (表头 list, 数据行 list[list])。"""
    path = os.path.join(STATIC_DIR, name + ".csv")
    if not os.path.exists(path):
        print(f"  ! 缺少 {path}，跳过")
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def add_line(text, every=12):
    """长文本每 every 个字符插入换行符，避免柱状图标签重叠（PDF 的 add_line 思路）。"""
    text = str(text)
    return "\n".join(text[i:i + every] for i in range(0, len(text), every))


def ensure_assets():
    """准备离线 assets：本地缺失则尝试从 CDN 下载；无网则回退 CDN_HOST。"""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    import urllib.request
    all_ok = True
    for fn in ASSET_FILES:
        dst = os.path.join(ASSETS_DIR, fn)
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            continue
        try:
            urllib.request.urlretrieve(CDN_HOST + fn, dst)
            print(f"  → 下载 assets/{fn}")
        except Exception as e:
            print(f"  ! 下载 {fn} 失败（{e}），该资源将回退在线 CDN")
            all_ok = False
    if not all_ok:
        # 任一文件下载失败，整体回退在线 host，保证图能显示
        CurrentConfig.ONLINE_HOST = CDN_HOST
        print(f"  ! assets 不全，ONLINE_HOST 回退为 {CDN_HOST}（需联网看图）")


def render(chart, name):
    os.makedirs(HTML_DIR, exist_ok=True)
    path = os.path.join(HTML_DIR, name + ".html")
    chart.render(path)
    inject_background(path)
    print(f"  → 生成 {path}")


# ---------------------------------------------------------------------------
# ① 各互动指标 Top10 视频 + Top10 UP 柱状图（Page 上下布局）
# ---------------------------------------------------------------------------
def make_metric_pages():
    for key, cn in METRICS:
        head_v, rows_v = read_csv(f"{key}_video")
        head_u, rows_u = read_csv(f"{key}_up")
        if rows_v is None or rows_u is None:
            continue
        print(f"[绘图] ① {cn}：Top10 视频 + Top10 UP")

        # 视频柱状图（title, 指标值）
        titles = [add_line(r[0]) for r in rows_v]
        vals_v = [int(r[1]) for r in rows_v]
        bar_v = (
            Bar()
            .add_xaxis(titles)
            .add_yaxis(cn, vals_v, label_opts=opts.LabelOpts(is_show=False))
            .set_global_opts(
                title_opts=opts.TitleOpts(title=f"{cn}最多的 Top10 视频"),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(
                    rotate=30, font_size=9, interval=0)),
                datazoom_opts=[opts.DataZoomOpts(type_="inside")],
            )
        )

        # UP 柱状图（up, 累计指标值）
        ups = [add_line(r[0]) for r in rows_u]
        vals_u = [int(r[1]) for r in rows_u]
        bar_u = (
            Bar()
            .add_xaxis(ups)
            .add_yaxis(f"累计{cn}", vals_u, label_opts=opts.LabelOpts(is_show=False))
            .set_global_opts(
                title_opts=opts.TitleOpts(title=f"累计{cn}最多的 Top10 UP 主"),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(
                    rotate=30, font_size=9, interval=0)),
            )
        )

        page = Page(layout=Page.SimplePageLayout)
        page.add(bar_v, bar_u)
        render(page, key)


# ---------------------------------------------------------------------------
# ② 收录次数：柱状图 + 富文本饼图（Grid 左右布局）
# ---------------------------------------------------------------------------
def make_count_page(csv_name, label_col, html_name, title):
    head, rows = read_csv(csv_name)
    if rows is None:
        return
    print(f"[绘图] ② 收录次数：{title}")
    names = [r[0] for r in rows]
    counts = [int(r[1]) for r in rows]

    bar = (
        Bar()
        .add_xaxis([add_line(n, 6) for n in names])
        .add_yaxis("收录次数", counts, label_opts=opts.LabelOpts(is_show=False))
        .set_global_opts(
            title_opts=opts.TitleOpts(title=f"{title}（柱状图）"),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(
                rotate=30, font_size=9, interval=0)),
            legend_opts=opts.LegendOpts(pos_top="6%"),
        )
    )

    pie = (
        Pie()
        .add(
            "收录次数",
            [list(z) for z in zip(names, counts)],
            center=["78%", "55%"],
            radius=["30%", "60%"],
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title=f"{title}（占比）", pos_left="60%"),
            legend_opts=opts.LegendOpts(is_show=False),
        )
        .set_series_opts(label_opts=opts.LabelOpts(formatter="{b}: {c} ({d}%)"))
    )

    grid = (
        Grid()
        .add(bar, grid_opts=opts.GridOpts(pos_right="55%", pos_bottom="20%"))
        .add(pie, grid_opts=opts.GridOpts())
    )
    render(grid, html_name)


# ---------------------------------------------------------------------------
# ③ 词云（title/desc/rcmd_reason 三个 WordCloud，Page 布局）
# ---------------------------------------------------------------------------
def make_wordcloud():
    fields = [("title_wordcount", "视频标题"),
              ("desc_wordcount", "视频简介"),
              ("rcmd_reason_wordcount", "推荐理由")]
    page = Page(layout=Page.SimplePageLayout)
    drew = False
    for name, cn in fields:
        head, rows = read_csv(name)
        if rows is None:
            continue
        print(f"[绘图] ③ 词云：{cn}")
        data = [(r[0], int(r[1])) for r in rows if r[0]]
        wc = (
            WordCloud()
            .add(cn, data, word_size_range=[12, 70], shape="circle")
            .set_global_opts(title_opts=opts.TitleOpts(title=f"{cn} 词云"))
        )
        page.add(wc)
        drew = True
    if drew:
        render(page, "wordcloud")


# ---------------------------------------------------------------------------
# ④ 相关性热力图
# ---------------------------------------------------------------------------
def make_correlation():
    head, rows = read_csv("correlation")
    if rows is None:
        return
    print("[绘图] ④ 斯皮尔曼相关性热力图")
    # correlation.csv：首列 feature，其后是各特征列
    feats = [r[0] for r in rows]
    cn_map = dict(zip(FEATURES, FEATURES_CN))
    labels = [cn_map.get(f, f) for f in feats]
    data = []
    for i, r in enumerate(rows):
        for j in range(len(feats)):
            data.append([i, j, round(float(r[j + 1]), 2)])
    heat = (
        HeatMap()
        .add_xaxis(labels)
        .add_yaxis(
            "相关系数", labels, data,
            label_opts=opts.LabelOpts(is_show=True, position="inside"),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="各互动指标斯皮尔曼相关性热力图"),
            visualmap_opts=opts.VisualMapOpts(min_=-1, max_=1, is_calculable=True,
                                              pos_left="left"),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=20)),
        )
    )
    render(heat, "correlation")


# ---------------------------------------------------------------------------
# ④ 分类器 Accuracy/AUC 双柱状图
# ---------------------------------------------------------------------------
def make_classifier():
    head, rows = read_csv("classifier_performance")
    if rows is None:
        return
    print("[绘图] ④ 分类器性能双柱状图")
    models = [r[0] for r in rows]
    acc = [round(float(r[1]), 4) for r in rows]
    auc = [round(float(r[2]), 4) for r in rows]
    bar = (
        Bar()
        .add_xaxis(models)
        .add_yaxis("Accuracy", acc)
        .add_yaxis("AUC", auc)
        .set_global_opts(
            title_opts=opts.TitleOpts(title="四种分类器性能对比（Accuracy / AUC）"),
            yaxis_opts=opts.AxisOpts(min_=0, max_=1),
        )
    )
    render(bar, "classifier")


# ---------------------------------------------------------------------------
# ⑤ index.html 汇总跳转
# ---------------------------------------------------------------------------
def make_index():
    print("[绘图] ⑤ 生成 index.html 汇总页")
    links = []
    for key, cn in METRICS:
        if os.path.exists(os.path.join(HTML_DIR, key + ".html")):
            links.append((key + ".html", f"{cn}：Top10 视频与 UP 主"))
    extra = [
        ("subject.html", "收录次数最多的视频分区"),
        ("up_count.html", "收录次数最多的 UP 主"),
        ("wordcloud.html", "标题/简介/推荐理由 词云"),
        ("correlation.html", "互动指标相关性热力图"),
        ("classifier.html", "分类器性能对比（Accuracy/AUC）"),
    ]
    for fn, cn in extra:
        if os.path.exists(os.path.join(HTML_DIR, fn)):
            links.append((fn, cn))

    items = "\n".join(
        f'      <li><a href="{fn}" target="_blank">{cn}</a></li>' for fn, cn in links
    )
    wm_b64 = _WM_B64
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Bilibili《每周必看》数据分析 可视化汇总</title>
  <style>
    body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
            max-width: 760px; margin: 0 auto; padding: 40px 20px; color: #222;
            background-color: #fff5f9;
            background-image: url('data:image/svg+xml;base64,{wm_b64}');
            background-repeat: repeat; background-attachment: fixed; }}
    h1 {{ color: #fb7299; border-bottom: 3px solid #fb7299; padding-bottom: 10px; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ margin: 12px 0; }}
    a {{ display: block; padding: 14px 18px; background: #f6f7f8; border-radius: 8px;
         text-decoration: none; color: #333; transition: .2s; }}
    a:hover {{ background: #fb7299; color: #fff; }}
  </style>
</head>
<body>
  <h1>Bilibili《每周必看》数据分析 · 可视化汇总</h1>
  <p>点击下列条目，查看对应分析结果的可视化页面：</p>
  <ul>
{items}
  </ul>
</body>
</html>
"""
    os.makedirs(HTML_DIR, exist_ok=True)
    with open(os.path.join(HTML_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  → 生成 {os.path.join(HTML_DIR, 'index.html')}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("模块4 可视化  echarts_show.py")
    print("=" * 60)
    os.makedirs(HTML_DIR, exist_ok=True)
    ensure_assets()

    make_metric_pages()
    make_count_page("popular_subject", "tname", "subject", "收录次数最多的视频分区")
    make_count_page("popular_up", "up", "up_count", "收录次数最多的 UP 主")
    make_wordcloud()
    make_correlation()
    make_classifier()
    make_index()

    print("=" * 60)
    print(f"模块4 完成，所有 html 在 {HTML_DIR}/，入口 {HTML_DIR}/index.html")


if __name__ == "__main__":
    main()
