import os
import logging
import time
import pytz
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from flask import Flask, send_file, Response
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger # <--- 添加这行导入
import requests
import subprocess
import glob

# 导入项目中的其他模块
import rss_parser
import translate_news
import generate_rss
import github_sync

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)

# 创建 Flask 应用
app = Flask(__name__)

# 定义常量
FEED_FILE = "feed.xml"
DAILYNEWS_DIR = "dailynews"
TRANSLATE_DIR = "translate"
TIMEZONE_TOKYO = pytz.timezone('Asia/Tokyo')

# 初始化函数：在应用启动时从 GitHub 同步 feed.xml
def init_feed_from_github():
    """
    从 GitHub 获取 feed.xml 并与本地文件比较，
    使用较新的版本作为项目初始化的 feed.xml
    """
    logging.info("正在初始化 feed.xml...")
    
    # 获取远程 feed.xml
    remote_content, remote_sha = github_sync.get_remote_feed()
    
    # 检查本地是否存在 feed.xml
    local_exists = os.path.exists(FEED_FILE)
    
    if remote_content and local_exists:
        # 比较两个文件的 lastBuildDate
        try:
            # 解析远程 XML
            remote_tree = ET.ElementTree(ET.fromstring(remote_content))
            remote_channel = remote_tree.getroot().find('channel')
            remote_build_date = remote_channel.find('lastBuildDate').text if remote_channel.find('lastBuildDate') is not None else None
            
            # 解析本地 XML
            local_tree = ET.parse(FEED_FILE)
            local_channel = local_tree.getroot().find('channel')
            local_build_date = local_channel.find('lastBuildDate').text if local_channel.find('lastBuildDate') is not None else None
            
            logging.info(f"远程 lastBuildDate: {remote_build_date}")
            logging.info(f"本地 lastBuildDate: {local_build_date}")
            
            # 如果远程版本较新，则使用远程版本
            if remote_build_date and local_build_date:
                from email.utils import parsedate_to_datetime
                remote_date = parsedate_to_datetime(remote_build_date)
                local_date = parsedate_to_datetime(local_build_date)
                
                if remote_date > local_date:
                    logging.info("远程 feed.xml 较新，使用远程版本")
                    with open(FEED_FILE, 'w', encoding='utf-8') as f:
                        f.write(remote_content)
                else:
                    logging.info("本地 feed.xml 较新，保留本地版本")
            else:
                logging.warning("无法比较日期，保留本地版本")
        except Exception as e:
            logging.error(f"比较 feed.xml 版本时出错: {e}")
            logging.info("保留本地版本")
    elif remote_content:
        # 本地不存在但远程存在，使用远程版本
        logging.info("本地不存在 feed.xml，使用远程版本")
        with open(FEED_FILE, 'w', encoding='utf-8') as f:
            f.write(remote_content)
    elif local_exists:
        # 远程不存在但本地存在，保留本地版本
        logging.info("远程不存在 feed.xml，保留本地版本")
    else:
        # 两者都不存在，创建一个空的 feed.xml
        logging.info("本地和远程都不存在 feed.xml，创建空文件")
        generate_rss.build_rss_feed([], FEED_FILE)

# 定义 Flask 路由，提供 feed.xml 访问
@app.route('/feed.xml')
def serve_feed():
    """提供 feed.xml 文件访问"""
    if os.path.exists(FEED_FILE):
        return send_file(FEED_FILE, mimetype='application/rss+xml')
    else:
        return Response("Feed not found", status=404)

@app.route('/')
def index():
    """提供简单的首页"""
    return """
    <html>
        <head><title>「埼玉新闻」每日中文综述 RSS</title></head>
        <body>
            <h1>提示</h1>
            <p>这是「埼玉新闻」每日中文综述 RSS 服务。</p>
            <p><a href="/feed.xml">点击这里</a> 访问 RSS Feed。</p>
        </body>
    </html>
    """

# 自我 ping 函数
def ping_self():
    """ping 自己的 feed.xml 以保持服务活跃"""
    try:
        # 获取当前主机地址
        host = os.environ.get('HOST', 'localhost')
        port = os.environ.get('PORT', '5000')
        url = f"http://{host}:{port}/feed.xml"
        
        logging.info(f"正在 ping: {url}")
        response = requests.get(url, timeout=10)
        logging.info(f"Ping 结果: {response.status_code}")
    except Exception as e:
        logging.error(f"Ping 失败: {e}")

# 获取当天日期字符串（东京时间）
def get_today_date_str():
    """获取当前东京时间的日期字符串，格式为 YYYYMMDD"""
    now = datetime.now(TIMEZONE_TOKYO)
    return now.strftime('%Y%m%d')

# 执行 RSS 更新流程
def process_rss_update():
    """
    执行 RSS 更新流程：
    1. 调用 rss_parser.py
    2. 检查并处理新的 dailynews
    3. 检查并处理新的 translate
    4. 推送更新后的 feed.xml 到 GitHub
    """
    today_date = get_today_date_str()
    logging.info(f"开始执行 RSS 更新流程，当前日期: {today_date}")
    
    # 1. 调用 rss_parser.py
    logging.info("步骤 1: 执行 rss_parser.py")
    try:
        rss_parser.main()
    except Exception as e:
        logging.error(f"执行 rss_parser.py 失败: {e}")
    
    # 2. 检查 dailynews 目录中是否有当天的 .md 文件
    dailynews_file = os.path.join(DAILYNEWS_DIR, f"{today_date}.md")
    if os.path.exists(dailynews_file):
        logging.info(f"步骤 2: 发现当天的 dailynews 文件: {dailynews_file}")
        try:
            # 调用 translate_news.py 处理该文件
            translate_news.translate_file(dailynews_file)
        except Exception as e:
            logging.error(f"执行 translate_news.py 处理 {dailynews_file} 失败: {e}")
    else:
        logging.info(f"步骤 2: 未找到当天的 dailynews 文件: {dailynews_file}")
    
    # 3. 检查 translate 目录中是否有当天的 .md 文件
    translate_file = os.path.join(TRANSLATE_DIR, f"{today_date}.md")
    if os.path.exists(translate_file):
        logging.info(f"步骤 3: 发现当天的 translate 文件: {translate_file}")
        try:
            # 获取远程 feed.xml 的 SHA
            _, remote_sha = github_sync.get_remote_feed()
            
            # 特别处理：只处理当天的 .md 文件，不重写整个 feed.xml
            # 这里我们需要修改 generate_rss.py 的行为，只处理单个文件
            
            # 1. 获取现有条目
            existing_items = generate_rss.get_existing_items(FEED_FILE)
            existing_guids = {item['guid'] for item in existing_items}
            
            # 2. 处理新文件
            item_data = generate_rss.parse_md_file(translate_file)
            if item_data and item_data['guid'] not in existing_guids:
                # 3. 合并并排序
                all_items = [item_data] + existing_items
                # 按 pubDate 排序（最新的在前）
                all_items.sort(key=lambda x: x.get('pubDate') or datetime.min.replace(tzinfo=datetime.timezone.utc), reverse=True)
                # 限制数量
                final_items = all_items[:generate_rss.MAX_ITEMS]
                
                # 4. 构建并写入
                generate_rss.build_rss_feed(final_items, FEED_FILE)
                logging.info(f"已将 {translate_file} 添加到 feed.xml")
            else:
                logging.info(f"文件 {translate_file} 已存在于 feed.xml 中或无法解析")
            
            # 4. 推送更新后的 feed.xml 到 GitHub
            if os.path.exists(FEED_FILE):
                logging.info("步骤 4: 推送更新后的 feed.xml 到 GitHub")
                commit_message = f"Update feed.xml with {today_date} news"
                github_sync.push_feed_to_github(FEED_FILE, commit_message, remote_sha)
            else:
                logging.error("步骤 4: feed.xml 不存在，无法推送")
        except Exception as e:
            logging.error(f"处理 translate 文件或推送到 GitHub 失败: {e}")
    else:
        logging.info(f"步骤 3: 未找到当天的 translate 文件: {translate_file}")

# 初始化调度器
def init_scheduler():
    """初始化定时任务调度器"""
    scheduler = BackgroundScheduler()

    # 添加东京时间 22:00 的 RSS 更新任务
    scheduler.add_job(
        process_rss_update,
        trigger=CronTrigger(hour=22, minute=0, timezone=TIMEZONE_TOKYO),
        id='daily_rss_update',
        name='Daily RSS Update at 22:00 Tokyo Time',
        replace_existing=True
    )

    # 添加每 5 分钟 ping 自己的任务 (Render free tier might sleep after 5 min inactivity)
    scheduler.add_job(
        ping_self,
        trigger=IntervalTrigger(minutes=5), # Slightly less than 5 min
        id='self_ping',
        name='Ping self every 5 minutes',
        replace_existing=True
    )

    scheduler.start()
    logging.info("调度器已启动")

# 不再需要 @app.before_first_request
# @app.before_first_request
# def initialize_app():
#     """应用首次请求前执行初始化"""
#     compare_and_update_feed()
#     init_scheduler()

# 在应用加载时直接执行初始化逻辑
init_feed_from_github() # <--- 将 compare_and_update_feed() 修改为 init_feed_from_github()
init_scheduler()

# 本地开发时运行
if __name__ == '__main__':
    # 获取端口号，Render 会设置 PORT 环境变量
    port = int(os.environ.get('PORT', 5000))
    # 允许外部访问，Render 需要 0.0.0.0
    app.run(host='0.0.0.0', port=port)