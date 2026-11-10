import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
import requests
from bs4 import BeautifulSoup

TARGET_URL = "https://www.gov.cn/guoqing/xxps/index.htm"
PUSHPLUS_URL = "https://www.pushplus.plus/send"
STATE_FILE = Path("pushed_ids.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

def load_state():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return set(data.get("pushed_ids", []))
        except Exception:
            return set()
    return set()

def save_state(ids):
    ids_list = list(ids)[-500:]
    STATE_FILE.write_text(json.dumps({"pushed_ids": ids_list}, ensure_ascii=False, indent=2), encoding="utf-8")

def make_id(title, link):
    return hashlib.md5(f"{title.strip()}|{link.strip()}".encode("utf-8")).hexdigest()

def fetch_articles():
    print(f"[TEST] 正在请求: {TARGET_URL}")
    try:
        resp = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
    except Exception as e:
        print(f"[TEST] 请求失败: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []
    
    for a_tag in soup.find_all("a", href=True):
        title = a_tag.get_text(strip=True)
        link = a_tag["href"].strip()

        if link.startswith("//"):
            link = "https:" + link
        elif link.startswith("/"):
            link = "https://www.gov.cn" + link
        elif link.startswith("./"):
            link = "https://www.gov.cn/guoqing/xxps/" + link[2:]

        if len(title) < 10 or "gov.cn" not in link:
            continue
        if "index" in link and title in ["首页", "返回首页"]:
            continue

        articles.append({"title": title, "link": link, "id": make_id(title, link)})
        
    return articles[:10]

def push_to_wechat(token, new_articles):
    if not new_articles: return True
    items_html = ""
    for idx, art in enumerate(new_articles, 1):
        items_html += f'<p>{idx}. <a href="{art["link"]}">{art["title"]}</a></p>\n'
    
    payload = {
        "token": token,
        "title": f"重要讲话更新 · {len(new_articles)} 条新内容",
        "content": f"<h3>政务网“重要讲话”专栏有新内容</h3>{items_html}",
        "template": "html",
    }
    try:
        resp = requests.post(PUSHPLUS_URL, json=payload, timeout=30)
        result = resp.json()
        if result.get("code") == 200:
            print(f"[TEST] 推送成功！")
            return True
        print(f"[TEST] 推送失败: {result}")
        return False
    except Exception as e:
        print(f"[TEST] 请求异常: {e}")
        return False

def main():
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        print("[TEST] 没找到 PUSHPLUS_TOKEN")
        return

    pushed_ids = load_state()
    print(f"[TEST] 已记录历史: {len(pushed_ids)} 条")

    articles = fetch_articles()
    print(f"[TEST] 真实提取到: {len(articles)} 条条目")

    new_articles = [a for a in articles if a["id"] not in pushed_ids]
    if not new_articles:
        print("[TEST] 没有新条目")
        return

    print(f"[TEST] 准备推送 {len(new_articles)} 条")
    if push_to_wechat(token, new_articles):
        pushed_ids.update(a["id"] for a in new_articles)
        save_state(pushed_ids)
        print("[TEST] 已保存状态")

if __name__ == "__main__":
    main()
