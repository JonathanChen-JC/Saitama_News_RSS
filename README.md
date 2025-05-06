# 埼玉新闻 RSS 项目

## 项目简介

这是一个自动化系统，用于抓取埼玉新闻的 RSS 源，将日语新闻翻译成中文，并生成 RSS Feed。该项目包含多个组件，共同工作以实现完整的新闻处理流程。

## 功能特点

- 自动抓取埼玉新闻 RSS 源
- 提取新闻内容并按日期分类
- 使用 Gemini API 将日语新闻翻译成中文
- 生成标准 RSS Feed
- 自动同步到 GitHub 仓库
- 提供 Web 服务访问 RSS Feed

## 环境要求

- Python 3.8+
- 以下 Python 包（详见 requirements.txt）:
  - flask>=2.0.0
  - requests>=2.26.0
  - feedparser>=6.0.8
  - beautifulsoup4>=4.10.0
  - pytz>=2021.3
  - markdown>=3.3.4
  - apscheduler>=3.8.1
  - lxml>=4.6.3

## 环境变量配置

项目需要以下环境变量：

| 环境变量 | 说明 | 默认值 |
|---------|------|-------|
| `GITHUB_TOKEN` | GitHub 个人访问令牌，用于访问 GitHub API | 无默认值，必须设置 |
| `GITHUB_REPO_URL` | GitHub 仓库 URL，格式为 `https://github.com/username/repo` | 无默认值，必须设置 |
| `HOST` | Web 服务主机地址 | localhost |
| `PORT` | Web 服务端口 | 5000 |
| `GEMINI_API_KEY` | Google Gemini API 密钥，用于翻译服务 | 无默认值，必须设置 |
| `GEMINI_MODEL` | 使用的 Gemini 模型名称 | gemini-2.5-pro-exp-03-25 |

## 项目结构

- `app.py`: Web 应用主程序，提供 RSS Feed 访问和定时任务调度
- `rss_parser.py`: 抓取和解析 RSS 源，生成日语新闻 Markdown 文件
- `translate_news.py`: 使用 Gemini API 将日语新闻翻译成中文
- `generate_rss.py`: 从翻译后的 Markdown 文件生成 RSS Feed
- `github_sync.py`: 同步 RSS Feed 到 GitHub 仓库
- `dailynews/`: 存放原始日语新闻的目录
- `translate/`: 存放翻译后中文新闻的目录
- `feed.xml`: 生成的 RSS Feed 文件

## 使用方法

### 1. 设置环境变量

在运行项目前，请确保设置了所有必要的环境变量：

```bash
# GitHub 相关配置
export GITHUB_TOKEN="your_github_token"
export GITHUB_REPO_URL="https://github.com/your_username/your_repo"

# Web 服务配置（可选）
export HOST="localhost"
export PORT="5000"

# Gemini API 配置
export GEMINI_API_KEY="your_gemini_api_key"
export GEMINI_MODEL="gemini-2.5-pro-exp-03-25"
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行 Web 服务

```bash
python app.py
```

### 4. 访问 RSS Feed

启动服务后，可以通过以下 URL 访问 RSS Feed：

```
http://localhost:5000/feed.xml
```

## 工作流程

1. `rss_parser.py` 定期抓取埼玉新闻 RSS 源，将新闻内容保存到 `dailynews/` 目录
2. `translate_news.py` 使用 Gemini API 将日语新闻翻译成中文，保存到 `translate/` 目录
3. `generate_rss.py` 从翻译后的文件生成 RSS Feed
4. `github_sync.py` 将生成的 RSS Feed 同步到 GitHub 仓库
5. `app.py` 提供 Web 服务，允许用户访问 RSS Feed

## 定时任务

系统配置了以下定时任务：

- 每天东京时间 22:00 执行 RSS 更新流程
- 每 5 分钟执行一次自我 ping，保持服务活跃