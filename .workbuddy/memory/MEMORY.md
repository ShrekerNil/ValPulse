# ValPulse 项目长期记忆

## 项目定位
D:\Repos\QLProjects\ValPulse：周度指数估值自动化系统。GitHub Actions 每周六 08:00（北京时间）跑流水线，报告部署 GitHub Pages，PushPlus 推微信。用户每周只看结果。

## 关键架构决策
- 数据源多级 fallback：乐咕（主）→ 中证官网（PE 兜底）→ 腾讯（行情）→ 东财（跨境）→ multpl（标普500）
- 乐咕限流是最大运维风险：8s 请求间隔 + 指数退避重试写死在 fetchers.LeguleguClient，勿调小 interval_seconds
- 口径：addTtmPe/addPb（加权，与中证官方整体法一致）；乐咕的 ttmPe/pb 是算术平均，不用
- 分位窗口近10年，剔除负 PE；分级 <20/20-70/70-90/>90
- 配色：涨红跌绿（A股惯例）；估值分位 绿=低估 蓝=合理 橙=偏高 红=高估

## 数据源速查（2026-10 验证）
- 乐咕：GET /stockdata/sz50-ttm-lyr 取 meta _csrf；token=md5(当天日期)；API /api/stockdata/index-basic-pe|index-basic-pb|hsidata(恒生)
- 中证：csindex-home/perf/index-perf?indexCode=000300&startDate=&endDate=（日频 PE）
- 腾讯：qt.gtimg.cn/q=sh000300，GBK，PE=[39] 涨跌幅=[32]；跨境代码需大写正则
- 东财：push2.eastmoney.com/api/qt/stock/get?secid=100.SPX（跨境兜底）
- multpl：/s-p-500-pe-ratio/table/by-month（月频）
- 失效：蛋卷、雪球、百度 opendata（指数）、乌龟量化、siblisresearch

## 用户偏好（本项目相关）
- 结论先行、最小代码、不过度工程
- 写/删除/配置修改需显式确认（git 本地 commit 可自行，push 远程需确认）
- 代码注释简体中文；Markdown 不硬编码标题编号
