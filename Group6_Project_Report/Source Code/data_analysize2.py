# -*- coding: utf-8 -*-
"""
data_analysize2.py —— 模块3：基于 Spark MLlib 的分析（严格按项目 PDF）

研究 ['view','danmaku','reply','favorite','coin','share','like'] 与历史排名 his_rank 的关系，
并训练分类器判断视频能否进入热搜榜前 10。

流程：
  HDFS/本地 textFile → RDD → Row → schema → DataFrame
  → 新增 label（his_rank<=10 → 1，否则 0）
  → VectorAssembler 组特征向量 → 8:2 划分训练/验证集
  → 斯皮尔曼相关系数（Correlation）            → ./static/correlation.csv
  → 逻辑回归/决策树/随机森林/GBT 四分类器
  → MulticlassClassificationEvaluator(Accuracy) + BinaryClassificationEvaluator(AUC)
                                                → ./static/classifier_performance.csv

可移植性（见 CLAUDE.md）：相对路径、UTF-8、HDFS 地址集中常量。
运行：
  本地无 HDFS 调试：  python data_analysize2.py
  Ubuntu/HDFS 提交： spark-submit data_analysize2.py --hdfs
"""
import os
import sys

from pyspark.sql import SparkSession, Row
from pyspark.sql.types import StructType, StructField, StringType, LongType

from pyspark.ml.feature import VectorAssembler
from pyspark.ml.stat import Correlation
from pyspark.ml.classification import (
    LogisticRegression, DecisionTreeClassifier,
    RandomForestClassifier, GBTClassifier,
)
from pyspark.ml.evaluation import (
    MulticlassClassificationEvaluator, BinaryClassificationEvaluator,
)

# ---------------------------------------------------------------------------
# 路径 / HDFS 配置（集中常量，与 data_analysize1.py 保持一致）
# ---------------------------------------------------------------------------
HDFS_BASE = "hdfs://localhost:9000"                 # Ubuntu VM 上按实际改这一行
HDFS_INPUT = HDFS_BASE + "/user/hadoop/bilibili_week.txt"
# 本地调试用：用 as_uri() 正确编码路径（兼容含中文的目录，如 /home/thnu/桌面/Project）
from pathlib import Path
LOCAL_INPUT = Path("./Data/bilibili_week.txt").resolve().as_uri()

STATIC_DIR = "./static"

USE_HDFS = "--hdfs" in sys.argv
INPUT_PATH = HDFS_INPUT if USE_HDFS else LOCAL_INPUT

COLUMNS = [
    "period", "up", "title", "tname",
    "view", "danmaku", "reply", "favorite", "coin", "share", "like", "his_rank",
    "desc", "rcmd_reason",
]
# 参与建模的特征（与 PDF 一致）
FEATURES = ["view", "danmaku", "reply", "favorite", "coin", "share", "like"]


# ---------------------------------------------------------------------------
# 读数据：textFile → RDD → Row → schema → DataFrame
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
    print(f"[读取] DataFrame 完成，有效记录 {df.count()} 条")
    return df


def save_csv(pdf, name):
    os.makedirs(STATIC_DIR, exist_ok=True)
    path = os.path.join(STATIC_DIR, name + ".csv")
    pdf.to_csv(path, index=False, encoding="utf-8")
    print(f"  → 已保存 {path}")


# ---------------------------------------------------------------------------
# ① 数据处理：选特征 + 打 label + 组向量 + 8:2 划分
# ---------------------------------------------------------------------------
def prepare(df):
    # 选特征列与 his_rank，新增 label：his_rank<=10 → 1，否则 0
    data = df.select(FEATURES + ["his_rank"])
    data = data.withColumn(
        "label",
        (data["his_rank"] <= 10).cast("int"),
    )
    # 组特征向量
    assembler = VectorAssembler(inputCols=FEATURES, outputCol="features")
    data = assembler.transform(data).select("features", "label")

    # 8:2 划分训练/验证集（固定 seed 便于复现）
    train, test = data.randomSplit([0.8, 0.2], seed=42)
    print(f"[划分] 训练集 {train.count()} 条，验证集 {test.count()} 条")
    return data, train, test


# ---------------------------------------------------------------------------
# ② 斯皮尔曼相关系数 → correlation.csv
# ---------------------------------------------------------------------------
def spearman_correlation(spark, data):
    print("[分析] ② 计算特征间斯皮尔曼相关系数")
    row = Correlation.corr(data, "features", "spearman").head()
    matrix = row[0].toArray()       # n×n 矩阵
    import pandas as pd
    pdf = pd.DataFrame(matrix, index=FEATURES, columns=FEATURES)
    pdf.insert(0, "feature", FEATURES)   # 首列写特征名，方便可视化构造 [i,j,value]
    save_csv(pdf, "correlation")


# ---------------------------------------------------------------------------
# ③ 四种分类器训练 + 评估 → classifier_performance.csv
# ---------------------------------------------------------------------------
def train_classifiers(spark, train, test):
    print("[分析] ③ 训练并评估 逻辑回归 / 决策树 / 随机森林 / GBT")
    classifiers = {
        "LogisticRegression": LogisticRegression(
            labelCol="label", featuresCol="features", maxIter=15),
        "DecisionTree": DecisionTreeClassifier(
            labelCol="label", featuresCol="features"),
        "RandomForest": RandomForestClassifier(
            labelCol="label", featuresCol="features"),
        "GBT": GBTClassifier(
            labelCol="label", featuresCol="features"),
    }

    acc_eval = MulticlassClassificationEvaluator(
        labelCol="label", predictionCol="prediction", metricName="accuracy")
    auc_eval = BinaryClassificationEvaluator(
        labelCol="label", rawPredictionCol="rawPrediction", metricName="areaUnderROC")

    records = []
    for name, clf in classifiers.items():
        model = clf.fit(train)
        pred = model.transform(test)
        acc = acc_eval.evaluate(pred)
        auc = auc_eval.evaluate(pred)
        print(f"    {name:18s}  Accuracy={acc:.4f}  AUC={auc:.4f}")
        records.append({"model": name, "accuracy": round(acc, 4), "auc": round(auc, 4)})

    import pandas as pd
    save_csv(pd.DataFrame(records), "classifier_performance")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("模块3 Spark MLlib 分析  data_analysize2.py")
    print(f"数据源模式：{'HDFS' if USE_HDFS else '本地 file:// 调试'}")
    print("=" * 60)

    spark = (
        SparkSession.builder
        .appName("BilibiliWeekMLlib")
        .master("local[*]")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    df = build_dataframe(spark)
    data, train, test = prepare(df)
    spearman_correlation(spark, data)
    train_classifiers(spark, train, test)

    spark.stop()
    print("=" * 60)
    print(f"模块3 完成，结果已写入 {STATIC_DIR}/")


if __name__ == "__main__":
    main()
