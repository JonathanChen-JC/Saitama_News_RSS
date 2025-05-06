import os
import requests
import base64
import logging
from urllib.parse import urlparse

# --- 配置日志 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 从环境变量读取配置 ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL")
FEED_FILE_PATH = "feed.xml" # 相对于仓库根目录的文件路径

def parse_repo_url(url):
    """从 GitHub URL 解析 owner 和 repo 名称"""
    if not url:
        return None, None
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) >= 2 and parsed.netloc == "github.com":
            owner = path_parts[0]
            repo = path_parts[1].replace('.git', '') # 移除可能的 .git 后缀
            return owner, repo
        else:
            logging.error(f"无法从 URL 解析 owner 和 repo: {url}")
            return None, None
    except Exception as e:
        logging.error(f"解析 URL 时出错 {url}: {e}")
        return None, None

OWNER, REPO = parse_repo_url(GITHUB_REPO_URL)

def get_github_api_headers(token):
    """构造 GitHub API 请求头"""
    if not token:
        raise ValueError("GITHUB_TOKEN 环境变量未设置")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

def get_remote_feed():
    """从 GitHub 仓库获取 feed.xml 的内容和 SHA"""
    if not OWNER or not REPO:
        logging.error("无法确定 GitHub owner 或 repo。请检查 GITHUB_REPO_URL。")
        return None, None

    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{FEED_FILE_PATH}"
    headers = get_github_api_headers(GITHUB_TOKEN)

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            content_base64 = data.get("content")
            sha = data.get("sha")
            if content_base64 and sha:
                content_bytes = base64.b64decode(content_base64)
                content = content_bytes.decode('utf-8')
                logging.info(f"成功从 GitHub 获取 '{FEED_FILE_PATH}' (SHA: {sha})")
                return content, sha
            else:
                logging.error("GitHub API 响应缺少 content 或 sha")
                return None, None
        elif response.status_code == 404:
            logging.info(f"远程仓库中未找到 '{FEED_FILE_PATH}'。将创建新文件。")
            return None, None # 文件不存在，返回 None SHA
        else:
            logging.error(f"获取远程 feed 失败: {response.status_code} - {response.text}")
            return None, None
    except requests.exceptions.RequestException as e:
        logging.error(f"请求 GitHub API 时出错: {e}")
        return None, None
    except Exception as e:
        logging.error(f"处理 GitHub API 响应时发生意外错误: {e}")
        return None, None


def push_feed_to_github(local_file_path, commit_message, remote_sha):
    """将本地 feed.xml 推送到 GitHub 仓库"""
    if not OWNER or not REPO:
        logging.error("无法确定 GitHub owner 或 repo。请检查 GITHUB_REPO_URL。")
        return False

    if not os.path.exists(local_file_path):
        logging.error(f"本地文件未找到: {local_file_path}")
        return False

    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{FEED_FILE_PATH}"
    headers = get_github_api_headers(GITHUB_TOKEN)

    try:
        with open(local_file_path, 'rb') as f:
            content_bytes = f.read()

        content_base64 = base64.b64encode(content_bytes).decode('utf-8')

        data = {
            "message": commit_message,
            "content": content_base64,
            "branch": "main" # 或者你的默认分支名
        }

        # 如果 remote_sha 存在，说明是更新现有文件，需要提供 SHA
        if remote_sha:
            data["sha"] = remote_sha
        # 如果 remote_sha 为 None，说明是创建新文件，不需要 SHA

        response = requests.put(url, headers=headers, json=data)

        if response.status_code == 200:
            logging.info(f"成功更新远程 '{FEED_FILE_PATH}'")
            return True
        elif response.status_code == 201:
            logging.info(f"成功创建远程 '{FEED_FILE_PATH}'")
            return True
        else:
            logging.error(f"推送 feed 到 GitHub 失败: {response.status_code} - {response.text}")
            # 尝试解析错误信息
            try:
                error_data = response.json()
                logging.error(f"GitHub API 错误详情: {error_data.get('message', '无详细信息')}")
            except Exception:
                pass # 如果响应不是 JSON 或解析失败，忽略
            return False

    except requests.exceptions.RequestException as e:
        logging.error(f"请求 GitHub API 时出错: {e}")
        return False
    except Exception as e:
        logging.error(f"读取本地文件或处理推送时发生意外错误: {e}")
        return False

# --- 主执行逻辑（用于测试或独立运行） ---
if __name__ == "__main__":
    if not GITHUB_TOKEN or not GITHUB_REPO_URL:
        print("错误：请设置 GITHUB_TOKEN 和 GITHUB_REPO_URL 环境变量。")
    else:
        print(f"配置: Owner={OWNER}, Repo={REPO}")

        # 1. 尝试获取远程文件
        print(f"\n--- 正在尝试从 GitHub 获取 {FEED_FILE_PATH} ---")
        remote_content, current_sha = get_remote_feed()

        if remote_content is not None:
            print(f"成功获取远程内容 (SHA: {current_sha})。内容片段：")
            print(remote_content[:200] + "...")
            # 可以选择将内容写入本地文件进行测试
            # with open("remote_test_" + FEED_FILE_PATH, "w", encoding="utf-8") as f:
            #     f.write(remote_content)
            # print("远程内容已写入 remote_test_feed.xml")
        elif current_sha is None and remote_content is None:
             print(f"远程文件 {FEED_FILE_PATH} 不存在或获取失败。")
        else: # current_sha is None but remote_content is None (file not found case)
             print(f"远程文件 {FEED_FILE_PATH} 不存在。")


        # 2. 准备一个本地文件用于测试推送 (假设 feed.xml 已由 generate_rss.py 生成)
        if os.path.exists(FEED_FILE_PATH):
            print(f"\n--- 正在尝试将本地 {FEED_FILE_PATH} 推送到 GitHub ---")
            commit_msg = f"Update {FEED_FILE_PATH} via script"
            success = push_feed_to_github(FEED_FILE_PATH, commit_msg, current_sha)
            if success:
                print("推送成功！")
            else:
                print("推送失败。")
        else:
            print(f"\n跳过推送测试，因为本地文件 {FEED_FILE_PATH} 不存在。")
            print("请先运行 generate_rss.py 生成 feed.xml。")