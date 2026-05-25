# 科创50公司财务与行情网页

本项目基于 HTML 原型改造，支持展示科创50成分股的公司基本信息、三大财务报表和行情数据。

## 功能

- 公司基本信息：公司名称与代码、主营业务构成、所属行业与细分赛道
- 三大财务报表：资产负债表、利润表、现金流量表
- 行情数据：最近交易日开高低收、成交量、成交额、流通股本、换手率
- 股票选择器：支持在多只科创50成分股之间切换

## 目录结构

```text
.
├── index.html                      # 完整网页，可读取 data/star50_data.json
├── prototype.html                  # 原始网页原型备份
├── data/
│   └── star50_data.json            # 采集后的网页数据
├── scripts/
│   └── fetch_star50_data.py         # AKShare 数据采集脚本
├── render.yaml                     # Render Static Site 配置
├── vercel.json                     # Vercel 静态部署配置
├── .nojekyll                       # GitHub Pages 静态站点标记
└── .gitignore
```

## 本地预览

```bash
python -m http.server 8000
```

浏览器访问：

```text
http://localhost:8000/index.html
```

## 生成数据

测试采集 1 只股票：

```bash
python scripts/fetch_star50_data.py --limit 1 --output ../data/star50_data.json
```

采集完整科创50：

```bash
python scripts/fetch_star50_data.py --output ../data/star50_data.json
```

完整采集会调用较多 AKShare 接口，预计需要数分钟。脚本已加入间隔，避免请求过快。

## GitHub Pages 部署

1. 将本目录推送到 GitHub 仓库。
2. 打开 GitHub 仓库：`Settings -> Pages`。
3. Source 选择 `Deploy from a branch`。
4. Branch 选择 `main`，目录选择 `/root`。
5. 保存后等待部署完成。

## Render Static Site 部署

推荐配置：

```text
Type: Static Site
Root Directory: 留空（如果仓库根目录就是本项目）
Build Command: 留空
Publish Directory: .
```

如果本项目在仓库子目录 `star50-web/` 下，则：

```text
Root Directory: star50-web
Build Command: 留空
Publish Directory: .
```

## 数据限制说明

- 公司基本信息中的主营业务和行业信息来自 AKShare 的雪球接口，通常比新浪财经更完整。
- 三大财务报表和行情数据使用 AKShare 新浪财经相关接口。
- 新浪利润表通常不直接提供“扣非净利润”，如果接口字段缺失，网页会显示为“—”。
- 行情数据展示最近一个有数据的交易日；如果当天休市或数据尚未更新，不会强制显示当天空数据。
