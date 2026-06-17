# HDFS 操作指导（VM 上用真 Spark 跑，严格按 PDF）

> 为什么要这步：PDF 要求数据**存到 HDFS**、Spark **从 HDFS 读**。
> Mac 本地的 `static/*.csv`、`html/` 是 pandas 预览版，**最终结果必须在 VM 上跑真 Spark 生成**。
> 环境：老师的 Ubuntu 虚拟机（用户 `thnu`），项目在 `~/桌面/Project/`，已装 Hadoop 3.1.3。
> 脚本里 HDFS 地址常量：`hdfs://localhost:9000`，数据路径 `/user/hadoop/bilibili_week.txt`。

---

## 第 1 步：启动 HDFS

```bash
start-dfs.sh        # 启动 NameNode + DataNode + SecondaryNameNode
jps                 # 验证：应同时看到 NameNode、DataNode、SecondaryNameNode
```
`jps` 里这三个都在 = HDFS 正常启动。**少了 NameNode 或 DataNode** 见文末"常见问题"。

> 若提示 `start-dfs.sh: command not found`：说明 PATH 没含 Hadoop，先
> `export PATH=$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$PATH`（老师镜像一般已配好）。

## 第 2 步：把清洗后的数据上传到 HDFS

确保已在项目目录、且 `bilibili_week.txt` 已由 `data_process.py` 生成：
```bash
cd ~/桌面/Project
ls bilibili_week.txt                       # 确认文件在

hdfs dfs -mkdir -p /user/hadoop            # 建目标目录（已存在不报错）
hdfs dfs -put -f bilibili_week.txt /user/hadoop/   # 上传(-f 覆盖旧的)
```
> 也可以一条命令搞定：`python data_process.py --upload`（脚本内部就是上面两句）。

## 第 3 步：验证上传成功

```bash
hdfs dfs -ls /user/hadoop                  # 能看到 bilibili_week.txt 及大小
hdfs dfs -cat /user/hadoop/bilibili_week.txt | head -2   # 看前两行内容
```
也可以浏览器打开 **HDFS 网页界面**（Hadoop 3.x 是 9870 端口）：
`http://localhost:9870` → Utilities → Browse the file system → 进 `/user/hadoop` 看到文件。

📷 这一步的 `hdfs dfs -ls` 输出 / 网页截图 = 报告【截图6：HDFS 上传成功】。

## 第 4 步：用真 Spark 从 HDFS 跑分析（生成最终 csv/html）

```bash
# 模块2：Spark SQL（--hdfs 让脚本读 hdfs://localhost:9000/user/hadoop/bilibili_week.txt）
spark-submit data_analysize1.py --hdfs
# 或：python data_analysize1.py --hdfs

# 模块3：Spark MLlib
spark-submit data_analysize2.py --hdfs

# 模块4：可视化（读 ./static/*.csv 生成 ./html/）
python echarts_show.py
```
跑完：
```bash
ls static/   # 21 个 csv（真 Spark 结果）
ls html/     # 14 个 html + index.html
```
这套 csv/html 才是**符合 PDF 的最终结果**（分类器 Acc/AUC 以这里 Spark MLlib 跑出的为准，本地 pandas 预览值仅供参考）。

## 第 5 步：（可选）停止 HDFS

```bash
stop-dfs.sh
```

---

## 不走 HDFS 也能跑（快速本地验证）

脚本默认用本地 `file://` 读 txt，不加 `--hdfs` 即可，不需要启动 Hadoop：
```bash
python data_analysize1.py      # file:// 本地
python data_analysize2.py
python echarts_show.py
```
> 但报告要体现"数据上传 HDFS、Spark 从 HDFS 读"，所以**正式截图请用 `--hdfs`** 那套。

---

## 常见问题

| 现象 | 原因 / 解决 |
|------|-------------|
| `jps` 里没有 DataNode | 多次格式化导致 clusterID 不一致。删掉 `/tmp/hadoop-*/dfs/data` 后重 `start-dfs.sh`；或 `stop-dfs.sh` → 删 data 目录 → `start-dfs.sh` |
| `Connection refused` 连 9000 | NameNode 没起来。先 `jps` 确认，没 NameNode 就看日志 `$HADOOP_HOME/logs/*namenode*.log` |
| `Name node is in safe mode` | 刚启动在安全模式，等 30 秒；急用：`hdfs dfsadmin -safemode leave` |
| 首次启动报 NameNode 未格式化 | 仅第一次需要：`hdfs namenode -format`（**会清空 HDFS，慎用，只第一次**），再 `start-dfs.sh` |
| `put` 报 File exists | 加 `-f` 覆盖：`hdfs dfs -put -f bilibili_week.txt /user/hadoop/` |
| Spark 报连不上 HDFS | 确认脚本顶部 `HDFS_BASE = "hdfs://localhost:9000"` 与 `core-site.xml` 里 `fs.defaultFS` 一致；端口有的环境是 8020，按实际改这一行 |
| `spark-submit: command not found` | 用 `python data_analysize1.py --hdfs` 代替（pyspark 自带 Spark，效果一样） |

> 一句话流程：`start-dfs.sh` → `data_process.py --upload` → `data_analysize1/2.py --hdfs` → `echarts_show.py` → 截图。
> 本文件仅用于 VM 上操作，不属于最终交付 zip。
