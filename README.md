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

## 部署（Gitee Go + Cloudflare Pages，全免费）

整体链路：Gitee Go 每周六 08:00 定时运行（国内 runner，网速快）→ 抓取计算生成报告 → PushPlus 推送微信 → wrangler 直传部署到 Cloudflare Pages（自动更新，无需手动）。

### 1. 创建 Gitee 仓库并推送

```bash
cd ValPulse
git remote add origin https://gitee.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

### 2. 配置 Cloudflare Pages

1. 注册/登录 https://dash.cloudflare.com （可用微信/ GitHub 账号）
2. 右侧菜单 → Compute & AI → Workers & Pages → Create → Pages → Direct Upload → 项目名填 `valpulse`（与流水线一致）
3. 右上角头像 → My Profile → API Tokens → Create Token → Custom token：权限选 Account / Cloudflare Pages / Edit，创建后复制 token
4. 同一页面左侧能看到 Account ID，复制

### 3. 配置 Gitee 流水线变量（密文）

Gitee 仓库页面 → 管理 → 流水线变量 → 新建，以下 4 个**全部勾选"密文"**：

| 变量名 | 值 |
| --- | --- |
| `PUSHPLUS_TOKEN` | pushplus.plus 扫码登录后复制的 token（免费 200 条/天） |
| `CLOUDFLARE_API_TOKEN` | 上一步创建的 Pages Edit token |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Account ID |
| `GITEE_PUSH_URL` | `https://<用户名>:<私人令牌>@gitee.com/<用户名>/<仓库名>.git` |

> `GITEE_PUSH_URL` 里的私人令牌：Gitee → 设置 → 私人令牌 → 生成新令牌，勾选 `projects` 权限。它用于流水线把每期数据快照推回仓库（下周环比要用）。未配置时流水线仍能跑，仅丢失环比功能。

### 4. 开启并测试流水线

Gitee 仓库页面 → 流水线（顶部导航）→ 选中 `指数估值周报` → 手动执行一次。全流程约 4-6 分钟（乐咕限速是主要耗时）。

执行成功后，Cloudflare Pages 项目页面的 `valpulse.pages.dev` 即为周报地址，国内访问速度中等偏好。之后每周六 08:00 自动运行，无需任何人工操作。

> 若 Gitee Go 的 YAML 报 schema 错误（Gitee 版本迭代可能导致），用网页可视化编辑器新建流水线：选一个 Shell 步骤，把 `.gitee/workflows/weekly.yml` 中 `run:` 后的命令原样粘入即可，功能等价。

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
data/snapshots/           # 每期快照（环比与审计，由流水线自动回推）
reports/                  # 生成的周报（本地查看用，不入库；线上由 Cloudflare Pages 托管）
.gitee/workflows/         # Gitee Go 定时流水线
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
