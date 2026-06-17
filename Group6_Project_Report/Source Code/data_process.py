# -*- coding: utf-8 -*-
"""
data_process.py —— 模块1：数据清洗与合并（严格按项目 PDF 规则）

流程：
  ./data/week_*.json  →  Pandas 选字段 / 去空去重 / 去异常 / 补文本  →  合并去表头
  →  bilibili_week.txt（制表符分隔、UTF-8、LF）  →  上传 HDFS（可选）

可移植性铁律（见 CLAUDE.md）：全部相对路径、UTF-8、LF、字段内清掉 \t\n\r 后用 \t 分隔。
运行：  python data_process.py            # 仅清洗，生成 txt
       python data_process.py --upload   # 清洗后再上传 HDFS（需 Ubuntu 上 Hadoop 已启动）
"""
import os
import glob
import json
import sys
import subprocess

import pandas as pd

# ---------------------------------------------------------------------------
# 路径与 HDFS 配置（集中常量，换机器只改这里）
# ---------------------------------------------------------------------------
DATA_DIR = "./Data"                       # 源数据 json 目录（与 Data 文件夹同名，json 平放其中）
OUTPUT_TXT = "./Data/bilibili_week.txt"   # 清洗后输出（写回 Data 文件夹）
HDFS_TARGET_DIR = "/user/hadoop"          # HDFS 目标目录（Ubuntu VM 上按实际改）

# 清洗后 txt 的列顺序（必须与 data_analysize1.py 的 schema 严格一致）
FINAL_COLS = [
    "period", "up", "title", "tname",
    "view", "danmaku", "reply", "favorite", "coin", "share", "like", "his_rank",
    "desc", "rcmd_reason",
]
# 互动数值字段：异常判定用（这些 <=0 视为异常）
NUM_POSITIVE_COLS = ["view", "danmaku", "reply", "favorite", "coin", "share", "like", "his_rank"]


def clean_text(s):
    """规范化文本：清掉换行符、Tab、回车，去首尾空白，避免破坏 \t 分隔。"""
    if s is None:
        return ""
    if isinstance(s, float) and pd.isna(s):
        return ""
    s = str(s)
    for ch in ("\t", "\n", "\r"):
        s = s.replace(ch, " ")
    return s.strip()


def parse_one_json(path):
    """解析单期 json，返回该期所有视频的记录 list（dict）。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    block = data.get("data") or {}
    config = block.get("config") or {}
    period = config.get("name", "")          # 期数，如 "2021第100期 02.12 - 02.18"
    rows = []
    for it in block.get("list", []):
        owner = it.get("owner") or {}
        stat = it.get("stat") or {}
        rows.append({
            "period": period,
            "up": owner.get("name"),
            "title": it.get("title"),
            "tname": it.get("tname"),
            "view": stat.get("view"),
            "danmaku": stat.get("danmaku"),
            "reply": stat.get("reply"),
            "favorite": stat.get("favorite"),
            "coin": stat.get("coin"),
            "share": stat.get("share"),
            "like": stat.get("like"),
            "his_rank": stat.get("his_rank"),
            "dislike": stat.get("dislike"),         # 仅用于异常判定，最后删列
            "desc": it.get("desc"),
            "rcmd_reason": it.get("rcmd_reason"),
        })
    return rows


def main():
    print("=" * 60)
    print("模块1 数据清洗  data_process.py")
    print("=" * 60)

    files = sorted(glob.glob(os.path.join(DATA_DIR, "week_*.json")))
    print(f"[读取] 在 {DATA_DIR} 找到 {len(files)} 个 json 文件")

    all_rows, bad_files = [], 0
    for path in files:
        try:
            all_rows.extend(parse_one_json(path))
        except Exception as e:
            bad_files += 1
            print(f"  ! 跳过无法解析的文件 {os.path.basename(path)}: {e}")
    print(f"[读取] 解析成功，原始视频记录 {len(all_rows)} 条"
          + (f"（{bad_files} 个文件解析失败）" if bad_files else ""))

    df = pd.DataFrame(all_rows)
    n0 = len(df)

    # --- 1) 数值字段转数字（无法转的置空，后续按空值删除）---
    num_cols = NUM_POSITIVE_COLS + ["dislike"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # --- 2) 删除空值（核心字段缺失即删；desc/rcmd_reason 允许空，后面补）---
    core_cols = ["up", "title", "tname"] + num_cols
    df = df.dropna(subset=core_cols)
    n1 = len(df)
    print(f"[去空值] 删除核心字段含空值的行：{n0 - n1} 条  →  剩 {n1} 条")

    # --- 3) 去重（up 主名字与视频标题同时相同视为重复）---
    df = df.drop_duplicates(subset=["up", "title"])
    n2 = len(df)
    print(f"[去重复] 删除 up+title 重复的行：{n1 - n2} 条  →  剩 {n2} 条")

    # --- 4) 去异常（互动数/his_rank<=0 或 dislike>0 视为异常）---
    cond_normal = (df[NUM_POSITIVE_COLS] > 0).all(axis=1) & (df["dislike"] <= 0)
    df = df[cond_normal]
    n3 = len(df)
    print(f"[去异常] 删除互动数≤0 或 dislike>0 的行：{n2 - n3} 条  →  剩 {n3} 条")

    # dislike 已无意义，删列
    df = df.drop(columns=["dislike"])

    # --- 5) 文本处理：desc/rcmd_reason 为空用 title 填充，并清掉特殊符号 ---
    for c in ["period", "up", "title", "tname", "desc", "rcmd_reason"]:
        df[c] = df[c].map(clean_text)
    empty_desc = (df["desc"] == "").sum()
    empty_rcmd = (df["rcmd_reason"] == "").sum()
    df.loc[df["desc"] == "", "desc"] = df["title"]
    df.loc[df["rcmd_reason"] == "", "rcmd_reason"] = df["title"]
    print(f"[补文本] 用标题填充空 desc {empty_desc} 条、空 rcmd_reason {empty_rcmd} 条")

    # --- 6) 数值字段转回 int，整理列顺序 ---
    for c in NUM_POSITIVE_COLS:
        df[c] = df[c].astype(int)
    df = df[FINAL_COLS]

    # --- 7) 去表头保存为制表符分隔 txt（UTF-8 / LF，字段已无 \t\n\r）---
    with open(OUTPUT_TXT, "w", encoding="utf-8", newline="\n") as f:
        for row in df.itertuples(index=False):
            f.write("\t".join(str(x) for x in row) + "\n")
    size_kb = os.path.getsize(OUTPUT_TXT) / 1024
    print(f"[保存] 已写出 {OUTPUT_TXT}：{len(df)} 行、{len(FINAL_COLS)} 列、{size_kb:.1f} KB")
    print(f"[保存] 列顺序：{' | '.join(FINAL_COLS)}")

    # --- 8) 上传 HDFS（可选）---
    if "--upload" in sys.argv:
        upload_to_hdfs()
    else:
        print("\n[HDFS] 未上传。Ubuntu 上 Hadoop 启动后，可执行：")
        print(f"       hdfs dfs -mkdir -p {HDFS_TARGET_DIR}")
        print(f"       hdfs dfs -put -f {OUTPUT_TXT} {HDFS_TARGET_DIR}/")
        print("       或重跑：python data_process.py --upload")
    print("=" * 60)
    print("模块1 完成")


def upload_to_hdfs():
    """把 bilibili_week.txt 上传到 HDFS（需 Hadoop 已启动、hdfs 命令在 PATH）。"""
    try:
        subprocess.run(["hdfs", "dfs", "-mkdir", "-p", HDFS_TARGET_DIR], check=True)
        subprocess.run(["hdfs", "dfs", "-put", "-f", OUTPUT_TXT, HDFS_TARGET_DIR + "/"], check=True)
        print(f"[HDFS] 上传成功 → {HDFS_TARGET_DIR}/bilibili_week.txt")
        subprocess.run(["hdfs", "dfs", "-ls", HDFS_TARGET_DIR])
    except FileNotFoundError:
        print("[HDFS] 未找到 hdfs 命令——请确认在 Ubuntu 上且 Hadoop 已启动、已配置 PATH。")
    except subprocess.CalledProcessError as e:
        print(f"[HDFS] 上传失败：{e}")


if __name__ == "__main__":
    main()
