# 大数据分析哔哩哔哩播放

Bilibili《每周必看》栏目数据分析 —— 大数据课程小组课题。

对 B 站《每周必看》收录的视频与 UP 主数据做完整流水线：
**采集 → 清洗 → HDFS → Spark SQL → Spark MLlib → pyecharts 可视化**。

## 项目结构

| 文件 | 说明 |
|------|------|
| `get_bilibili_week.py` | 模块0 爬虫：请求官方 API 抓每期 JSON（随机 UA / retry） |
| `data_process.py` | 模块1 清洗：选字段 / 去空去重 / 去异常 / 补文本 → `bilibili_week.txt` |
| `data_analysize1.py` | 模块2 Spark SQL：Top10 UP/分区、各互动指标 Top10、jieba 词频 Top300 |
| `data_analysize2.py` | 模块3 Spark MLlib：标签 + 8:2 切分 + 斯皮尔曼 + LR/DT/RF/GBT |
| `echarts_show.py` | 模块4 可视化：柱状/饼/词云/热力图/双柱 + `html/index.html` 汇总 |
| `chineseStopWords.txt` | 中文停用词（jieba 用） |
| `requirements.txt` | 第三方依赖 |
| `data/` | 采集得到的每期 JSON（304 期） |
| `bilibili_week.txt` | 清洗后数据（Tab 分隔 / UTF-8 / LF），上传 HDFS |
| `static/` | Spark 分析结果 csv |
| `html/` | pyecharts 可视化结果（入口 `index.html`） |

## 运行环境

Ubuntu 22.04 · Python 3.8 · Hadoop 3.1.3 · Spark 3.2.0 · Anaconda

```bash
pip install -r requirements.txt
python data_process.py            # 清洗
python data_analysize1.py --hdfs  # Spark SQL（默认 file:// 本地调试）
python data_analysize2.py --hdfs  # MLlib
python echarts_show.py            # 可视化 → html/
```
