import feedparser
import requests
from bs4 import BeautifulSoup
import pytz
from datetime import datetime
import os
import time
import logging

# --- 配置 ---
RSS_URL = "https://news.yahoo.co.jp/rss/media/saitama/all.xml"
OUTPUT_DIR = "dailynews"
TIMEZONE_TOKYO = pytz.timezone('Asia/Tokyo')
TIMEZONE_GMT = pytz.utc

# --- 日志设置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 辅助函数 ---
def parse_gmt_date(parsed_struct):
    """使用 feedparser 解析好的 time.struct_time 创建 timezone-aware datetime 对象"""
    if not parsed_struct:
        return None
    try:
        # 从 time.struct_time 创建 naive datetime 对象
        # time.mktime 期望本地时间元组，但 feedparser 的 struct_time 通常是 GMT/UTC
        # 我们使用 calendar.timegm 将 UTC struct_time 转为 Unix 时间戳
        import calendar
        timestamp = calendar.timegm(parsed_struct)
        dt_naive = datetime.utcfromtimestamp(timestamp)
        # 设置时区为 GMT/UTC
        dt_gmt = TIMEZONE_GMT.localize(dt_naive)
        return dt_gmt
    except Exception as e:
        logging.error(f"从 parsed_struct 创建 datetime 时出错: {e}")
        return None

def convert_to_tokyo_time(dt_gmt):
    """将 GMT datetime 对象转换为东京时间"""
    if dt_gmt and dt_gmt.tzinfo:
        return dt_gmt.astimezone(TIMEZONE_TOKYO)
    elif dt_gmt:
        # 如果是 naive datetime，先假定它是 GMT
        logging.warning("接收到 naive datetime，假定为 GMT")
        dt_gmt_aware = TIMEZONE_GMT.localize(dt_gmt)
        return dt_gmt_aware.astimezone(TIMEZONE_TOKYO)
    return None

def scrape_article_content(url):
    """抓取指定 URL 的文章内容"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status() # 如果请求失败则抛出异常
        response.encoding = response.apparent_encoding # 尝试自动检测编码

        soup = BeautifulSoup(response.text, 'html.parser')

        # --- 尝试定位文章主体内容 ---
        # Yahoo News Japan 的结构可能会变化，以下是一些可能的选择器
        # 优先尝试更具体的 class 或 id
        article_body = soup.find('div', class_=lambda x: x and 'article_body' in x.lower())
        if not article_body:
             article_body = soup.find('article') # 尝试 <article> 标签
        if not article_body:
            article_body = soup.find('div', id='uamods-pickup') # 另一个可能的容器
        if not article_body:
             article_body = soup.find('div', class_='articleBody') # 备选 class

        # --- 提取文本 ---
        if article_body:
            # 移除脚本和样式标签
            for script_or_style in article_body(['script', 'style']):
                script_or_style.decompose()

            # 获取所有段落文本，并合并
            paragraphs = article_body.find_all('p')
            if paragraphs:
                 content = '\n'.join(p.get_text(strip=True) for p in paragraphs)
            else:
                 # 如果没有 p 标签，尝试获取整个容器的文本
                 content = article_body.get_text(separator='\n', strip=True)
            return content.strip()
        else:
            logging.warning(f"在 {url} 未找到明确的文章主体容器。")
            # 作为最后的手段，尝试提取 body 的主要文本，但这可能包含很多无关内容
            body_text = soup.body.get_text(separator='\n', strip=True) if soup.body else "无法提取 Body 内容"
            # 可以加一些启发式规则来清理，但这里简单返回部分内容
            return body_text[:1000] + "..." # 限制长度以防抓取整个页面

    except requests.exceptions.RequestException as e:
        logging.error(f"请求文章失败 {url}: {e}")
    except Exception as e:
        logging.error(f"抓取或解析文章失败 {url}: {e}")
    return "无法抓取文章内容。"

# --- 主逻辑 ---
def main():
    logging.info("开始处理 RSS 源...")

    # 1. 创建输出目录
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logging.info(f"创建目录: {OUTPUT_DIR}")

    # 2. 获取并解析 RSS 源
    try:
        logging.info(f"正在获取 RSS 源: {RSS_URL}")
        feed_data = feedparser.parse(RSS_URL)
    except Exception as e:
        logging.error(f"获取或解析 RSS 源失败: {e}")
        return

    if feed_data.bozo:
        logging.warning(f"RSS 源可能格式不正确: {feed_data.bozo_exception}")

    if not feed_data.entries:
        logging.info("RSS 源中没有找到新闻条目。")
        return

    logging.info(f"找到 {len(feed_data.entries)} 条新闻。开始处理...")

    # 3. 按日期分组存储新闻
    news_by_date = {}

    # 4. 遍历条目
    for entry in feed_data.entries:
        title = entry.title
        link = entry.link
        # 直接获取 feedparser 解析好的日期结构
        published_parsed = entry.get('published_parsed')

        if not published_parsed:
            pub_date_str = entry.get('published', '未知日期') # 获取原始字符串用于日志
            logging.warning(f"条目 '{title}' ({pub_date_str}) 缺少解析后的日期，跳过。")
            continue

        # 5. 处理日期和时间
        # 将解析好的 struct_time 传递给函数
        dt_gmt = parse_gmt_date(published_parsed)
        if not dt_gmt:
            pub_date_str = entry.get('published', '未知日期')
            logging.warning(f"无法处理条目 '{title}' 的日期 '{pub_date_str}'，跳过。")
            continue

        dt_tokyo = convert_to_tokyo_time(dt_gmt)
        if not dt_tokyo:
             logging.warning(f"无法将条目 '{title}' 的日期转换为东京时间，跳过。")
             continue

        date_str_yyyymmdd = dt_tokyo.strftime('%Y%m%d')
        # 格式化时间字符串供显示
        time_str_tokyo_display = dt_tokyo.strftime('%Y-%m-%d %H:%M:%S %Z%z')

        logging.info(f"处理文章: {title} (发布于东京时间: {time_str_tokyo_display})")

        # 6. 抓取文章内容
        logging.info(f"  正在抓取: {link}")
        content = scrape_article_content(link)
        # 添加短暂延时防止过快请求
        time.sleep(0.5)

        # 7. 存储到字典
        if date_str_yyyymmdd not in news_by_date:
            news_by_date[date_str_yyyymmdd] = []

        # 同时存储格式化后的字符串和原始的 datetime 对象
        news_by_date[date_str_yyyymmdd].append({
            'title': title,
            'link': link,
            'published_tokyo_str': time_str_tokyo_display, # 用于显示的字符串
            'published_tokyo_dt': dt_tokyo,             # 用于排序的 datetime 对象
            'content': content
        })

    # 8. 写入 Markdown 文件
    logging.info("所有文章处理完毕，开始写入文件...")
    for date_str, articles in news_by_date.items():
        filepath = os.path.join(OUTPUT_DIR, f"{date_str}.md")
        logging.info(f"  正在写入: {filepath} ({len(articles)} 篇文章)")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {date_str} 新闻\n\n")
                # 按发布时间排序（使用 datetime 对象）
                articles.sort(key=lambda x: x['published_tokyo_dt']) # 直接使用 datetime 对象排序

                for article in articles:
                    f.write(f"## {article['title']}\n\n")
                    # 使用之前格式化好的字符串写入文件
                    f.write(f"**发布时间:** {article['published_tokyo_str']}\n")
                    f.write(f"**链接:** {article['link']}\n\n")
                    f.write("### 全文内容:\n")
                    f.write(f"{article['content']}\n\n")
        except IOError as e:
            logging.error(f"写入文件失败 {filepath}: {e}")
        except Exception as e:
            logging.error(f"处理或写入文件时发生未知错误 {filepath}: {e}")

    logging.info("脚本执行完毕。")

if __name__ == "__main__":
    main()