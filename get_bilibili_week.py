from faker import Faker
import requests
import os
import json
import time
import brotli
from retry import retry


import csv

filename = "webURL_Error.csv"

def save_errorurl_csv(url):
    with open(filename, 'a', newline='', encoding='utf-8') as file:
        # 创建 CSV 写入器
        writer = csv.writer(file)
        # 将链接追加到CSV文件中
        writer.writerow([url])
        print(f"成功添加 URL ~~~~~~~~")



@retry()
def get_weekdata_json(url, json_path):
    # 随机 User-Agent
    fake = Faker()

    # headers信息，添加user-agent和cookies
    # headers = {
    #     "User-Agent": random_UA,
    #     "Referer": "https://www.bilibili.com/",
    #     "Origin": "https://www.bilibili.com/",
    #     "Accept": "application/json, text/plain, */*",
    #     "Connection": "keep-alive"
    # }

    # （原此处的真实 Cookie 已移除，公开 API 不需要）
    # headers = {
    #     "User-Agent": random_UA,
    #     "Referer": "https://www.bilibili.com",
    #     # User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0
    #     "Accept": "application/xml",
    #     "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    #     "Accept-Encoding": "gzip, deflate, br, zstd",
    #     "Connection": "keep-alive"

    # }

    # 《每周必看》是公开 API，无需登录 Cookie。
    # 如遇风控需要 Cookie，可从浏览器开发者工具复制后填入下方（切勿把真实 Cookie 提交到公开仓库）。
    cookies = {}

    headers = {
        "User-Agent": fake.user_agent(),
        #'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Referer': 'https://www.bilibili.com',
        'Origin': 'https://www.bilibili.com',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Priority': 'u=4',
        'TE': 'trailers',
    }




    # 获取响应，转换为json格式保存
    response = requests.get(url=url, headers=headers, cookies=cookies)
    print(f'已获取 URL: {url}, 状态码：{response.status_code}')
    print("Content-Encoding:", response.headers.get("Content-Encoding"))

    if response.status_code == 200:
        try:
            # 手动处理 Brotli 解压
            if response.headers.get("Content-Encoding") == "br":
                content = brotli.decompress(response.content).decode("utf-8")
            else:
                content = response.text

            # 尝试 JSON 解析
            response_data = json.loads(content)

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(response_data, f, ensure_ascii=False)

            print(f"成功保存至{json_path}")

        except Exception as e:
            print(f"[JSON 解析失败] 错误信息：{e}")
            print("原始响应内容片段：", response.content[:200])
            print("解析失败的网址为：", url)
            save_errorurl_csv(url)
            time.sleep(3)

    else:
        print(f'获取失败，状态码：{response.status_code}')
        time.sleep(20)

    # 休眠，确保不会被反爬
    time.sleep(2)


if __name__ == '__main__':
    # 官方 api
    url = 'https://api.bilibili.com/x/web-interface/popular/series/one?number={}'
    # 爬虫数据存储路径
    data_folder = './dat'
    os.makedirs(data_folder, exist_ok=True)

    # 开始爬虫
    for i in range(20, 327):
        URL = url.format(str(i))
        # 每周数据存储路径
        json_fpath = os.path.join(data_folder, 'week_{}.json'.format(str(i)))
        get_weekdata_json(URL, json_fpath)
