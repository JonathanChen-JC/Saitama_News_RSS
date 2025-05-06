import os
import glob
import xml.etree.ElementTree as ET
from xml.dom import minidom
import markdown
from datetime import datetime, timezone
import logging
import re
from email.utils import format_datetime

# --- 配置 ---
TRANSLATE_DIR = "translate"
FEED_FILE = "feed.xml"
MAX_ITEMS = 50
FEED_TITLE = "「埼玉新闻」每日中文综述"
FEED_LINK = "https://github.com/your_username/your_repo" # 替换为你的项目链接
FEED_DESCRIPTION = "「埼玉新闻」每日中文综述 RSS"

# --- 配置日志 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_rfc822_date(date_str):
    """尝试解析 RFC 822 日期字符串"""
    try:
        # email.utils.parsedate_to_datetime 似乎更健壮
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception as e:
        logging.warning(f"无法解析日期字符串 '{date_str}': {e}")
        # 尝试其他格式或返回 None
        try:
            # 尝试 ISO 格式 (可能由旧脚本生成)
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            logging.error(f"无法将 '{date_str}' 解析为已知日期格式。")
            return None


def get_existing_items(feed_file):
    """解析现有的 feed.xml 文件并返回项目列表"""
    items = []
    if not os.path.exists(feed_file):
        return items

    try:
        tree = ET.parse(feed_file)
        root = tree.getroot()
        # RSS 2.0 没有命名空间，但以防万一
        ns = {'': ''} # 假设没有默认命名空间或处理它
        channel = root.find('channel', ns)
        if channel is None:
             logging.warning(f"在 {feed_file} 中找不到 <channel> 元素")
             return items

        for item_elem in channel.findall('item', ns):
            item = {}
            title_elem = item_elem.find('title', ns)
            link_elem = item_elem.find('link', ns)
            description_elem = item_elem.find('description', ns)
            pubDate_elem = item_elem.find('pubDate', ns)
            guid_elem = item_elem.find('guid', ns)

            item['title'] = title_elem.text if title_elem is not None else "无标题"
            item['link'] = link_elem.text if link_elem is not None else ""
            item['description'] = description_elem.text if description_elem is not None else ""
            item['guid'] = guid_elem.text if guid_elem is not None else None # GUID 很重要

            pubDate_str = pubDate_elem.text if pubDate_elem is not None else None
            item['pubDate_str'] = pubDate_str
            item['pubDate'] = parse_rfc822_date(pubDate_str) if pubDate_str else None

            if item['guid']: # 只添加有 GUID 的项目
                items.append(item)
            else:
                logging.warning(f"跳过缺少 GUID 的项目: {item.get('title', '未知标题')}")

    except ET.ParseError as e:
        logging.error(f"解析 {feed_file} 失败: {e}. 将创建一个新的 feed。")
    except Exception as e:
        logging.error(f"读取或解析 {feed_file} 时发生意外错误: {e}")

    # 按日期排序，确保最新的在前面（如果日期有效）
    items.sort(key=lambda x: x['pubDate'] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items


def parse_md_file(md_file_path):
    """解析单个 .md 文件，提取信息并转换为 HTML"""
    try:
        filename_with_ext = os.path.basename(md_file_path)
        filename_no_ext = os.path.splitext(filename_with_ext)[0] # 获取不带扩展名的文件名

        with open(md_file_path, 'r', encoding='utf-8') as f:
            content_md = f.read()

        # 1. 修改 title 生成方式
        title = f"「埼玉新闻」{filename_no_ext}" # 使用固定前缀和文件名

        # 提取发布时间 (从 **发布时间:** 行) - 这部分逻辑保持不变
        pub_time_match = re.search(r'^\*\*发布时间:\*\*\s*(.*)', content_md, re.MULTILINE)
        pub_date_str_original = pub_time_match.group(1).strip() if pub_time_match else None
        pub_date = None
        if pub_date_str_original:
             # 尝试解析多种可能的格式
             try:
                 # 格式如: 2025-05-05 19:12:03 JST+0900
                 dt_naive_str = pub_date_str_original.split(' JST')[0]
                 dt_naive = datetime.strptime(dt_naive_str, '%Y-%m-%d %H:%M:%S')
                 jst = timezone(datetime.strptime('+0900', '%z').utcoffset())
                 pub_date = dt_naive.replace(tzinfo=jst)
             except ValueError as e:
                 logging.warning(f"无法解析文件 {md_file_path} 中的日期 '{pub_date_str_original}': {e}")


        # 如果无法从内容解析日期，则从文件名获取 - 这部分逻辑保持不变
        if not pub_date:
            try:
                # 假设文件名是 YYYYMMDD
                dt_naive = datetime.strptime(filename_no_ext, '%Y%m%d')
                jst = timezone(datetime.strptime('+0900', '%z').utcoffset())
                pub_date = dt_naive.replace(tzinfo=jst)
                logging.info(f"从文件名 {filename_with_ext} 解析日期为: {pub_date.isoformat()}")
            except ValueError:
                logging.warning(f"无法从文件名 {filename_with_ext} 解析日期。")
                mtime = os.path.getmtime(md_file_path)
                pub_date = datetime.fromtimestamp(mtime, timezone.utc)
                logging.info(f"使用文件修改时间: {pub_date.isoformat()}")

        # 2. 修改 link 生成方式
        # 注意：确保 FEED_LINK 末尾没有斜杠，或者这里处理好拼接
        link = f"{FEED_LINK.rstrip('/')}/{filename_with_ext}" # 使用仓库链接和完整文件名

        # 将 Markdown 转换为 HTML - 这部分逻辑保持不变
        # 可以移除标题、时间和链接行，避免在 description 中重复
        # 注意：由于 title 和 link 不再从 markdown 中提取，移除它们的步骤可以省略或调整
        content_body_md = re.sub(r'^##\s+.*\n?', '', content_md, count=1, flags=re.MULTILINE) # 仍然移除旧标题行
        content_body_md = re.sub(r'^\*\*发布时间:\*\*\s*.*\n?', '', content_body_md, count=1, flags=re.MULTILINE)
        content_body_md = re.sub(r'^\*\*链接:\*\*\s*.*\n?', '', content_body_md, count=1, flags=re.MULTILINE) # 仍然移除旧链接行
        content_html = markdown.markdown(content_body_md.strip())

        # 3. 修改 guid 生成方式
        guid = f"saitama_news_{filename_with_ext}" # 使用固定前缀和完整文件名

        return {
            'title': title,
            'link': link,
            'description': content_html,
            'pubDate': pub_date,
            'pubDate_str': format_datetime(pub_date) if pub_date else None, # RFC 822 格式
            'guid': guid
        }

    except Exception as e:
        logging.error(f"处理文件 {md_file_path} 时出错: {e}")
        return None

def build_rss_feed(items, feed_file):
    """构建 RSS XML 结构并写入文件"""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = FEED_TITLE
    ET.SubElement(channel, "link").text = FEED_LINK
    ET.SubElement(channel, "description").text = FEED_DESCRIPTION
    ET.SubElement(channel, "language").text = "zh-cn" # 语言设为中文

    # 添加当前时间作为 lastBuildDate
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))

    # 添加项目
    for item_data in items:
        item_elem = ET.SubElement(channel, "item")
        ET.SubElement(item_elem, "title").text = item_data['title']
        ET.SubElement(item_elem, "link").text = item_data['link']
        # 使用 CDATA 包装 HTML 内容
        description_elem = ET.SubElement(item_elem, "description")
        description_elem.text = f"<![CDATA[{item_data['description']}]]>"
        if item_data['pubDate_str']:
            ET.SubElement(item_elem, "pubDate").text = item_data['pubDate_str']
        ET.SubElement(item_elem, "guid", isPermaLink="false").text = item_data['guid'] # isPermaLink=false 因为 GUID 是文件名

    # 格式化输出 XML
    try:
        # 使用 minidom 进行美化输出
        xml_str = ET.tostring(rss, encoding='utf-8')
        dom = minidom.parseString(xml_str)
        pretty_xml_str = dom.toprettyxml(indent="  ", encoding='utf-8')

        with open(feed_file, 'wb') as f: # 以二进制写入 UTF-8 编码的 XML
            f.write(pretty_xml_str)
        logging.info(f"RSS feed 已成功生成/更新到: {feed_file}")
    except Exception as e:
        logging.error(f"写入 RSS feed 文件失败: {e}")


def main():
    """主函数"""
    logging.info("开始生成 RSS feed...")

    # 1. 获取现有条目
    existing_items = get_existing_items(FEED_FILE)
    existing_guids = {item['guid'] for item in existing_items}
    logging.info(f"从 {FEED_FILE} 加载了 {len(existing_items)} 个现有条目。")

    # 2. 查找 translate 目录下的 .md 文件
    md_files = glob.glob(os.path.join(TRANSLATE_DIR, "*.md"))
    if not md_files:
        logging.warning(f"在目录 {TRANSLATE_DIR} 中未找到 .md 文件。")
        # 如果没有 md 文件，但有旧 feed，则保留旧 feed
        if existing_items:
             logging.info("未找到新的 .md 文件，保留现有的 feed.xml。")
             # 可以选择重新写入以更新 lastBuildDate
             build_rss_feed(existing_items, FEED_FILE)
        else:
             logging.info("没有找到 .md 文件，也没有现有的 feed.xml。")
        return

    # 按文件名（日期）排序，确保处理顺序
    md_files.sort()

    # 3. 处理新的 .md 文件
    new_items = []
    processed_count = 0
    for md_file in md_files:
        # guid = os.path.basename(md_file) # <--- 旧代码
        filename_with_ext = os.path.basename(md_file) # 获取完整文件名
        guid = f"saitama_news_{filename_with_ext}" # <--- 修正：使用与 parse_md_file 一致的格式生成 GUID
        if guid not in existing_guids:
            logging.info(f"处理新文件: {md_file}")
            item_data = parse_md_file(md_file)
            if item_data:
                new_items.append(item_data)
                processed_count += 1
            else:
                 logging.warning(f"跳过无法处理的文件: {md_file}")

    logging.info(f"处理了 {processed_count} 个新文件。")

    # 4. 合并、排序和截断
    all_items = existing_items + new_items
    # 按 pubDate 排序（最新的在前），无效日期视为最早
    all_items.sort(key=lambda x: x.get('pubDate') or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # 限制数量
    final_items = all_items[:MAX_ITEMS]
    if len(all_items) > MAX_ITEMS:
        logging.info(f"条目数量超过 {MAX_ITEMS}，已截断为最新的 {len(final_items)} 条。")

    # 5. 构建并写入最终的 feed.xml
    build_rss_feed(final_items, FEED_FILE)

    logging.info("RSS feed 生成任务完成。")

if __name__ == "__main__":
    main()