# -*- coding: utf-8 -*-
"""
data_analysize1.py —— 模块2：基于 Spark SQL 的数据分析（严格按项目 PDF）

流程：
  HDFS textFile → RDD → map 按 \t 切分 → Row → 定义 schema → DataFrame
  → 注册临时视图 data → 一系列 Spark SQL 查询 → toPandas().to_csv() 存 ./static/

分析内容：
  ① 收录视频最多的 Top10 UP 主          → popular_up.csv
  ② 收录次数最多的 Top10 视频分区        → popular_subject.csv
  ③ 各互动指标(view/danmaku/reply/favorite/coin/share/like) 的
     Top10 视频 + Top10 UP 主           → <metric>_video.csv / <metric>_up.csv
  ④ title/desc/rcmd_reason 的 jieba 词频 Top300 → <field>_wordcount.csv

可移植性（见 CLAUDE.md）：相对路径、UTF-8、HDFS 地址集中常量、停用词相对路径加载。
运行：
  本地无 HDFS 调试：  python data_analysize1.py            # 用 file:// 读本地 txt
  Ubuntu/HDFS 提交： spark-submit data_analysize1.py --hdfs # 读 HDFS
"""
import os
import sys

import jieba

from pyspark.sql import SparkSession, Row
from pyspark.sql.types import (
    StructType, StructField, StringType, LongType,
)

# ---------------------------------------------------------------------------
# 路径 / HDFS 配置（集中常量，换机器只改这里）
# ---------------------------------------------------------------------------
HDFS_BASE = "hdfs://localhost:9000"                 # Ubuntu VM 上按实际改这一行
HDFS_INPUT = HDFS_BASE + "/user/hadoop/bilibili_week.txt"
# 本地调试用：用 as_uri() 正确编码路径（兼容含中文的目录，如 /home/thnu/桌面/Project）
from pathlib import Path
LOCAL_INPUT = Path("./bilibili_week.txt").resolve().as_uri()

STATIC_DIR = "./static"                             # 分析结果 csv 输出目录
STOPWORDS_FILE = "./chineseStopWords.txt"           # 中文停用词（jieba 用）

# 读取数据源：默认本地 file:// 调试；带 --hdfs 参数则读 HDFS
USE_HDFS = "--hdfs" in sys.argv
INPUT_PATH = HDFS_INPUT if USE_HDFS else LOCAL_INPUT

# 清洗后 txt 的列顺序（必须与 data_process.py 的 FINAL_COLS 严格一致）
COLUMNS = [
    "period", "up", "title", "tname",
    "view", "danmaku", "reply", "favorite", "coin", "share", "like", "his_rank",
    "desc", "rcmd_reason",
]
# 互动数值指标：分别出 Top10 视频 + Top10 UP
METRICS = ["view", "danmaku", "reply", "favorite", "coin", "share", "like"]
# 词频统计的文本字段
TEXT_FIELDS = ["title", "desc", "rcmd_reason"]
NUM_COLS = ["view", "danmaku", "reply", "favorite", "coin", "share", "like", "his_rank"]


# ---------------------------------------------------------------------------
# 停用词 & 分词
# ---------------------------------------------------------------------------
def load_stopwords():
    """从相对路径加载中文停用词集合。"""
    words = set()
    if os.path.exists(STOPWORDS_FILE):
        with open(STOPWORDS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip()
                if w:
                    words.add(w)
    else:
        print(f"[警告] 未找到停用词文件 {STOPWORDS_FILE}，分词将不去停用词")
    return words


# 停用词集合在 driver 上加载一次，闭包传给 executor
STOPWORDS = load_stopwords()


def pretty_cut(text):
    """jieba 对中文语句分词，去停用词、去空白与单字噪声，返回词语 list。"""
    if not text:
        return []
    result = []
    for word in jieba.cut(str(text)):
        word = word.strip()
        if not word:
            continue
        if word in STOPWORDS:
            continue
        if len(word) < 2:          # 过滤单字，词频更有意义
            continue
        result.append(word)
    return result


# ---------------------------------------------------------------------------
# Spark 初始化：textFile → RDD → Row → schema → DataFrame → 临时视图 data
# ---------------------------------------------------------------------------
def build_dataframe(spark):
    sc = spark.sparkContext
    print(f"[读取] 数据源：{INPUT_PATH}")
    raw = sc.textFile(INPUT_PATH)

    def to_row(line):
        p = line.split("\t")
        if len(p) != len(COLUMNS):
            return None
        try:
            return Row(
                period=p[0], up=p[1], title=p[2], tname=p[3],
                view=int(p[4]), danmaku=int(p[5]), reply=int(p[6]),
                favorite=int(p[7]), coin=int(p[8]), share=int(p[9]),
                like=int(p[10]), his_rank=int(p[11]),
                desc=p[12], rcmd_reason=p[13],
            )
        except ValueError:
            return None

    rows = raw.map(to_row).filter(lambda r: r is not None)

    schema = StructType([
        StructField("period", StringType(), True),
        StructField("up", StringType(), True),
        StructField("title", StringType(), True),
        StructField("tname", StringType(), True),
        StructField("view", LongType(), True),
        StructField("danmaku", LongType(), True),
        StructField("reply", LongType(), True),
        StructField("favorite", LongType(), True),
        StructField("coin", LongType(), True),
        StructField("share", LongType(), True),
        StructField("like", LongType(), True),
        StructField("his_rank", LongType(), True),
        StructField("desc", StringType(), True),
        StructField("rcmd_reason", StringType(), True),
    ])

    df = spark.createDataFrame(rows, schema)
    df.createOrReplaceTempView("data")
    print(f"[读取] 构建 DataFrame 完成，有效记录 {df.count()} 条，已注册临时视图 data")
    return df


# ---------------------------------------------------------------------------
# 结果落盘工具
# ---------------------------------------------------------------------------
def save_csv(sdf, name):
    """spark.DataFrame → pandas → ./static/<name>.csv（UTF-8）。"""
    os.makedirs(STATIC_DIR, exist_ok=True)
    path = os.path.join(STATIC_DIR, name + ".csv")
    sdf.toPandas().to_csv(path, index=False, encoding="utf-8")
    print(f"  → 已保存 {path}")


# ---------------------------------------------------------------------------
# ① 收录视频最多的 Top10 UP 主
# ---------------------------------------------------------------------------
def analyze_popular_up(spark):
    print("[分析] ① 收录视频最多的 Top10 UP 主")
    sdf = spark.sql("""
        SELECT up, COUNT(up) AS count
        FROM data GROUP BY up
        ORDER BY count DESC LIMIT 10
    """)
    save_csv(sdf, "popular_up")


# ---------------------------------------------------------------------------
# ② 收录次数最多的 Top10 视频分区
# ---------------------------------------------------------------------------
def analyze_popular_subject(spark):
    print("[分析] ② 收录次数最多的 Top10 视频分区")
    sdf = spark.sql("""
        SELECT tname, COUNT(tname) AS count
        FROM data GROUP BY tname
        ORDER BY count DESC LIMIT 10
    """)
    save_csv(sdf, "popular_subject")


# ---------------------------------------------------------------------------
# ③ 各互动指标的 Top10 视频 + Top10 UP 主
# ---------------------------------------------------------------------------
def analyze_metrics(spark):
    for m in METRICS:
        print(f"[分析] ③ {m}：Top10 视频 + Top10 UP 主")
        # Top10 视频：title + 指标值
        video = spark.sql(f"""
            SELECT title, {m}
            FROM data ORDER BY {m} DESC LIMIT 10
        """)
        save_csv(video, f"{m}_video")
        # Top10 UP：按 sum(指标) 分组降序
        up = spark.sql(f"""
            SELECT up, SUM({m}) AS total
            FROM data GROUP BY up
            ORDER BY total DESC LIMIT 10
        """)
        save_csv(up, f"{m}_up")


# ---------------------------------------------------------------------------
# ④ jieba 词频统计 Top300（title / desc / rcmd_reason）
# ---------------------------------------------------------------------------
def analyze_wordcount(spark):
    for field in TEXT_FIELDS:
        print(f"[分析] ④ 词频统计 Top300：{field}")
        rdd = (
            spark.sql(f"SELECT {field} FROM data").rdd
            .flatMap(lambda row: pretty_cut(row[field]))
            .map(lambda w: (w, 1))
            .reduceByKey(lambda a, b: a + b)
            .repartition(1)
            .sortBy(lambda kv: kv[1], ascending=False)
        )
        top = rdd.filter(lambda kv: kv[0] != "").take(300)
        sdf = spark.createDataFrame(
            [Row(word=w, count=c) for w, c in top],
            StructType([
                StructField("word", StringType(), True),
                StructField("count", LongType(), True),
            ]),
        )
        save_csv(sdf, f"{field}_wordcount")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("模块2 Spark SQL 分析  data_analysize1.py")
    print(f"数据源模式：{'HDFS' if USE_HDFS else '本地 file:// 调试'}")
    print("=" * 60)

    spark = (
        SparkSession.builder
        .appName("BilibiliWeekSparkSQL")
        .master("local[*]")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    build_dataframe(spark)
    analyze_popular_up(spark)
    analyze_popular_subject(spark)
    analyze_metrics(spark)
    analyze_wordcount(spark)

    spark.stop()
    print("=" * 60)
    print(f"模块2 完成，结果已写入 {STATIC_DIR}/")


if __name__ == "__main__":
    main()
