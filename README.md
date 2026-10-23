# ValPulse - 每周指数估值自动化系统

每周自动抓取主要指数估值数据，计算近 10 年 PE/PB 分位，生成可视化周报并推送到微信。全程无人值守：数据抓取、分位计算、图表生成、报告部署、消息推送全部自动完成。

## 功能

- **覆盖范围**：A 股宽基/行业/策略指数 12 个 + 跨境（标普500、恒生科技）
- **分位计算**：近 10 年窗口历史分位，剔除亏损期（PE 为负）样本
- **四级分级**：<20% 低估 / 20-70% 合理 / 70-90% 偏高 / >90% 高估
- **周报内容**：估值总表（含环比）、分位总览条形图、重点指数估值走势图
- **推送**：PushPlus 推送到微信（Markdown 摘要 + 完整报告链接）
- **配色**：涨红跌绿（A 股惯例）；估值分位绿=低估、红=高估

## 数据源（全部免费）

| 数据 | 来源 | 频率 |
| --- | --- | --- |
| A 股指数 PE/PB 历史（约2005年至今） | 乐咕乐股 | 日频（月末快照） |
| A 股指数 PE 兜底 | 中证指数官网 | 日频 |
| 指数行情/涨跌 | 腾讯行情 | 实时 |
| 标普500 PE 历史 | multpl.com | 月频 |
| 恒生科技 PE 历史 | 乐咕乐股（恒生指数公司数据） | 月频 |

口径说明：A 股 PE/PB 采用与中证官方整体法一致的加权口径（已交叉验证，差异 <5%）。

## 部署（GitHub Actions + Pages，全免费）

### 1. 创建仓库并推送代码

```bash
cd ValPulse
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

> 仓库公开可享无限 Actions 分钟；私有仓库每月 2000 分钟也远够用（本系统每周约 5 分钟）。

### 2. 配置 PushPlus

1. 打开 https://www.pushplus.plus/ ，微信扫码登录，复制你的 token
2. 仓库页面 → Settings → Secrets and variables → Actions → New repository secret
3. Name 填 `PUSHPLUS_TOKEN`，Value 填 token，保存

> 免费额度 200 条/天，个人使用足够。未配置 token 时流水线照常运行，仅跳过推送。

### 3. 开启 GitHub Pages

仓库页面 → Settings → Pages → Source 选择 `gh-pages` 分支 → Save

几分钟后访问 `https://<你的用户名>.github.io/<仓库名>/` 即可看到周报。国内访问慢的话本地开代理即可；微信推送摘要本身不受网络影响。

### 4. 定时任务

工作流已配置每周六 08:00（北京时间）自动运行。也可以在 Actions 页面点击 "Run workflow" 手动触发。

## 本地运行

```bash
pip install -r requirements.txt
python -m src.pipeline
```

报告生成在 `reports/<日期>/index.html`，最新报告在 `reports/index.html`。
本地推送需设置环境变量 `PUSHPLUS_TOKEN`。

## 目录结构

```
config.yaml               # 指数清单、分位阈值、抓取参数
src/
  fetchers.py             # 数据抓取（乐咕/中证/腾讯/multpl，限速与重试）
  percentile.py           # 近10年分位计算与分级
  charts.py               # matplotlib 图表
  report.py               # HTML 周报与归档页
  push.py                 # PushPlus 推送
  pipeline.py             # 主流程
data/snapshots/           # 每期快照（环比与审计，由 Actions 自动回推）
reports/                  # 生成的周报（Pages 托管，Actions 自动部署）
.github/workflows/        # GitHub Actions 定时任务
```

## 调整指数清单

编辑 `config.yaml` 的 `indexes` 列表即可增删指数（code 为乐咕代码格式，如 `000300.SH`）。
添加后首次运行会自动验证数据可用性，抓取失败的指数会在推送中告警。

乐咕已支持的主要指数代码示例：
`000300.SH` 沪深300、`000905.SH` 中证500、`000852.SH` 中证1000、`000016.SH` 上证50、
`399006.SZ` 创业板指、`000688.SH` 科创50、`000932.SH` 中证主要消费、`000933.SH` 中证医药卫生、
`399986.SZ` 中证银行、`000992.SH` 全指金融、`000922.CSI` 中证红利、`000015.SH` 上证红利。

## 常见问题

- **乐咕限流**：该站对频率敏感，已内置 8 秒请求间隔 + 指数退避重试。请勿调小 `interval_seconds`。
- **图表中文乱码**：工作流已安装 Noto CJK 字体；本地运行需系统有中文字体（微软雅黑/思源黑体）。
- **周报链接**：PushPlus 的 Markdown 链接需在 PushPlus 公众号/客户端内打开；完整报告建议直接访问 Pages 地址。
