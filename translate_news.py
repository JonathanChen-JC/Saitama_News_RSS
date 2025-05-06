import os
import sys
import glob
import logging
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

# --- 配置日志 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 加载环境变量 ---
load_dotenv()

# --- 配置 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro-exp-03-25")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

INPUT_DIR = "dailynews"
OUTPUT_DIR = "translate"

# --- 翻译提示词 ---
TRANSLATION_PROMPT = """你是一位专业的翻译者，擅长将日语新闻，翻译为简体中文，请对我给出的内容进行翻译。请遵循以下要求：

# 翻译格式

1. 使用Markdown格式输出
2. 将所有日语内容进行翻译，包括：标题、正文等
3. 输出时，完整保留原始内容中，所有无需翻译的内容，不要遗漏
4. 原始内容中的所有链接网址，不要改动

# 注意事项

1. 直接输出，不要加入任何与原始内容无关的回应性语句"""

def translate_with_gemini(content):
    """使用 Gemini API 翻译内容"""
    if not GEMINI_API_KEY:
        logging.error("未设置 GEMINI_API_KEY 环境变量")
        sys.exit(1)
    
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {"text": TRANSLATION_PROMPT},
                    {"text": content}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 1.0,
            "topP": 0.95,
            "topK": 40,
            "maxOutputTokens": 100000
        }
    }
    
    try:
        response = requests.post(
            GEMINI_API_URL,
            headers=headers,
            data=json.dumps(data),
            timeout=1000
        )
        response.raise_for_status()
        result = response.json()
        
        # 提取翻译后的文本
        if "candidates" in result and len(result["candidates"]) > 0:
            translated_text = result["candidates"][0]["content"]["parts"][0]["text"]
            return translated_text
        else:
            logging.error(f"API 响应中未找到翻译结果: {result}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"API 请求失败: {e}")
        return None
    except Exception as e:
        logging.error(f"翻译过程中发生错误: {e}")
        return None

def get_latest_md_file(directory):
    """获取指定目录下最新的 .md 文件"""
    md_files = glob.glob(os.path.join(directory, "*.md"))
    if not md_files:
        return None
    
    # 按文件修改时间排序，获取最新的文件
    latest_file = max(md_files, key=os.path.getmtime)
    return latest_file

def translate_file(input_file_path):
    """翻译指定的 .md 文件并保存结果"""
    # 确保输出目录存在
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logging.info(f"创建目录: {OUTPUT_DIR}")
    
    # 获取输出文件路径
    filename = os.path.basename(input_file_path)
    output_file_path = os.path.join(OUTPUT_DIR, filename)
    
    logging.info(f"开始翻译文件: {input_file_path}")
    
    try:
        # 读取输入文件内容
        with open(input_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 调用 Gemini API 进行翻译
        translated_content = translate_with_gemini(content)
        
        if translated_content:
            # 保存翻译结果
            with open(output_file_path, 'w', encoding='utf-8') as f:
                f.write(translated_content)
            logging.info(f"翻译完成，已保存到: {output_file_path}")
            return True
        else:
            logging.error(f"翻译失败: {input_file_path}")
            return False
    except Exception as e:
        logging.error(f"处理文件时发生错误: {e}")
        return False

def main():
    """主函数"""
    # 检查命令行参数
    if len(sys.argv) > 1:
        # 如果提供了文件名参数
        input_file = sys.argv[1]
        if not input_file.endswith('.md'):
            input_file += '.md'  # 自动添加扩展名
        input_file_path = os.path.join(INPUT_DIR, input_file)
    else:
        # 否则使用最新的 .md 文件
        input_file_path = get_latest_md_file(INPUT_DIR)
    
    if not input_file_path or not os.path.exists(input_file_path):
        logging.error(f"找不到要翻译的文件: {input_file_path}")
        sys.exit(1)
    
    # 翻译文件
    success = translate_file(input_file_path)
    
    if success:
        logging.info("翻译任务完成")
    else:
        logging.error("翻译任务失败")
        sys.exit(1)

if __name__ == "__main__":
    main()