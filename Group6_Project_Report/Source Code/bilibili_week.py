# -*- coding: utf-8 -*-
"""
get_bilibili_week.py —— 模块0：采集 B 站《每周必看》每期 JSON

官方接口 popular/series/one 现已启用 WBI 风控（不带签名直接返回 code=-352）。
本脚本：
  ① 起一个 Session，访问主页拿 buvid3，再从 nav 接口取 WBI 密钥算 mixin_key；
  ② 每次请求用 w_rid + wts 做 WBI 签名，绕过风控；
  ③ 自动从 list 接口取当前最新期数，增量抓取（已存在的 week_*.json 跳过）；
  ④ 只在 code==0 且 data 非空时保存，避免存下风控/未发布的错误响应。

可移植性（见 CLAUDE.md）：相对路径 ./data、UTF-8、ensure_ascii=False。
运行：  python get_bilibili_week.py        # 抓到最新一期（Linux 下更稳）
"""
import os
import csv
import json
import time
import hashlib
import urllib.parse
from functools import reduce

import requests
import brotli
from faker import Faker
from retry import retry

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DATA_DIR = "./Data"                       # 每期 json 存放目录（与 Data 文件夹同名）
ERR_FILE = "webURL_Error.csv"             # 失败 number 记录
ONE_API = "https://api.bilibili.com/x/web-interface/popular/series/one"   # 单期数据
LIST_API = "https://api.bilibili.com/x/web-interface/popular/series/list"  # 全部期列表
NAV_API = "https://api.bilibili.com/x/web-interface/nav"                   # WBI 密钥
# WBI mixin_key 重排表（B 站固定常量）
MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]


def save_errorurl_csv(number):
    with open(ERR_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([number])
    print(f"  记录失败期数 {number}")


# ---------------------------------------------------------------------------
# WBI 签名
# ---------------------------------------------------------------------------
def new_session():
    """新建带随机 UA 的 Session，访问主页获取 buvid3 等基础 cookie。"""
    s = requests.Session()
    s.headers.update({
        "User-Agent": Faker().user_agent(),
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
    })
    try:
        s.get("https://www.bilibili.com/", timeout=15)
    except Exception:
        pass
    return s


def get_mixin_key(session):
    """从 nav 接口取 WBI 的 img_key/sub_key，按固定表重排成 32 位 mixin_key。"""
    nav = session.get(NAV_API, timeout=15).json()
    img = nav["data"]["wbi_img"]["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub = nav["data"]["wbi_img"]["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    orig = img + sub
    return reduce(lambda acc, i: acc + orig[i], MIXIN_TAB, "")[:32]


def wbi_sign(params, mixin_key):
    """给参数加 wts 和 w_rid（WBI 签名）。"""
    params = dict(params)
    params["wts"] = int(time.time())
    query = "&".join(
        f"{k}={urllib.parse.quote(str(params[k]))}" for k in sorted(params)
    )
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------
@retry(tries=3, delay=2)
def get_weekdata_json(number, json_path, session, mixin_key):
    """抓取某一期数据并保存；成功返回 True，无有效数据/失败返回 False。"""
    params = wbi_sign({"number": number}, mixin_key)
    resp = session.get(ONE_API, params=params, timeout=15)

    if resp.status_code != 200:
        print(f"  第{number}期 HTTP {resp.status_code}")
        time.sleep(5)
        return False

    # 个别响应是 br 压缩，手动兜底解压
    if resp.headers.get("Content-Encoding") == "br":
        try:
            content = brotli.decompress(resp.content).decode("utf-8")
            data = json.loads(content)
        except Exception:
            data = resp.json()
    else:
        data = resp.json()

    # 只在有效时保存（code==0 且 data 非空）
    if data.get("code") != 0 or not data.get("data"):
        print(f"  第{number}期 无有效数据(code={data.get('code')})，跳过")
        time.sleep(1)
        return False

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    name = data["data"].get("config", {}).get("name", "")
    print(f"  ✓ 第{number}期已保存（{name}）")
    time.sleep(2)          # 防反爬
    return True


def get_latest_number(session):
    """从 list 接口取当前最新期数；失败返回 None。"""
    try:
        data = session.get(LIST_API, timeout=15).json()
        if data.get("code") == 0 and data.get("data", {}).get("list"):
            return max(x["number"] for x in data["data"]["list"])
    except Exception as e:
        print(f"[list] 取最新期数失败：{e}")
    return None


REFRESH_EVERY = 12        # 每抓这么多期就换新 Session，重置 B 站风控计数


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    session = new_session()
    mixin_key = get_mixin_key(session)
    print(f"[WBI] mixin_key 就绪：{mixin_key[:8]}...")

    latest = get_latest_number(session)
    if latest is None:
        latest = 400
        print(f"[提示] 未取到最新期数，使用保底上限 {latest}")
    else:
        print(f"[提示] B 站当前最新期：第 {latest} 期")

    # 只抓缺的；新期(期号大)优先，避免排到最后撞风控
    missing = [n for n in range(1, latest + 1)
               if not os.path.exists(os.path.join(DATA_DIR, f"week_{n}.json"))]
    missing.sort(reverse=True)
    skip_cnt = latest - len(missing)
    print(f"[提示] 待抓 {len(missing)} 期（已存在 {skip_cnt} 期跳过），新期优先")

    new_cnt = fail_cnt = 0
    for idx, number in enumerate(missing):
        # 每 REFRESH_EVERY 期换新 Session + 重新签名密钥，规避累计风控
        if idx and idx % REFRESH_EVERY == 0:
            print("  …换新 Session 重置风控…")
            time.sleep(3)
            session = new_session()
            mixin_key = get_mixin_key(session)

        json_path = os.path.join(DATA_DIR, f"week_{number}.json")
        try:
            if get_weekdata_json(number, json_path, session, mixin_key):
                new_cnt += 1
            else:
                fail_cnt += 1
                save_errorurl_csv(number)
        except Exception as e:
            print(f"  第{number}期 异常：{e}")
            fail_cnt += 1
            save_errorurl_csv(number)

    total = len([f for f in os.listdir(DATA_DIR) if f.endswith(".json")])
    print(f"\n完成：新增 {new_cnt} 期，跳过已存在 {skip_cnt} 期，失败 {fail_cnt} 期")
    print(f"{DATA_DIR} 现共 {total} 个 json")


if __name__ == "__main__":
    main()
