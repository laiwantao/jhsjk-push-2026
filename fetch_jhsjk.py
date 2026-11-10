#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# ================= 配置 =================
# 换成了中国政府网“习近平系列重要讲话”专栏，无防爬，极其稳定
TARGET_URL = "https://www.gov.cn/guoqing/xxps/index.htm"
PUSHPLUS_URL = "https://www.pushplus.plus/send"
STATE_FILE = Path("pushed_ids.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
# =======================================

def load_state() -> set:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return set(data.get("pushed_ids", []))
        except Exception:
            return set()
    return set()

def save_state(ids: set) -> None:
    ids_list = list(ids)[-500:]
    STATE_FILE.write_text(
        json.dumps({"pushed_ids": ids_list}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def make_id(title: str, link: str) -> str:
    raw = f"{title.strip()}|{link.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def fetch_articles() -> list:
    print(f"[INFO] 正在请求网页: {TARGET_URL}")
    try:
        resp = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
    except Exception as e:
        print(f"[ERROR] 网页请求失败: {e}")
        return []
        
    print(f"[DEBUG] 网页内容快照: {resp.text[:500]}")
    articles = []
    
    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []
    seen_links = set()

    # 抓取页面中所有的链接
    for a_tag in soup.find_all("a", href=True):
        title = a_tag.get_text(strip=True)
        link = a_tag["href"].strip()

        # 补全相对链接
        if link.startswith("//"):
            link = "https:" + link
        elif link.startswith("/"):
            link = "https://www.gov.cn" + link
        elif link.startswith("./"):
            link = "https://www.gov.cn/guoqing/xxps/" + link[2:]

        # 过滤：标题太短或不是政府网链接的跳过
        if len(title) < 10:
            continue
        if "gov.cn" not in link:
            continue
            
        # 过滤掉导航栏（比如“首页”、“网站地图”等）
        if "index" in link and title in ["首页", "返回首页"]:
            continue

        if link in seen_links:
            continue

        seen_links.add(link)
        articles.append({"title": title, "link": link, "id": make_id(title, link)})

    # 只取最新的 10 条
    return articles[:10]

def push_to_wechat(token: str, new_articles: list) -> bool:
    if not new_articles:
        return True

    items_html = ""
    for idx, art in enumerate(new_articles, 1):
        items_html += f'<p>{idx}. <a href="{art["link"]}" target="_blank">{art["title"]}</a></p>\n'

    content = (
        f"<h3>政务网“重要讲话”专栏有新内容</h3>\n"
        f"<p>共 {len(new_articles)} 条新条目：</p>\n"
        f"{items_html}\n"
        f"<hr>\n"
        f"<p style='color:#888;font-size:12px;'>抓取时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
    )

    payload = {
        "token": token,
        "title": f"重要讲话更新 · {len(new_articles)} 条新内容",
        "content": content,
        "template": "html",
    }

    try:
        resp = requests.post(PUSHPLUS_URL, json=payload, timeout=30)
        result = resp.json()
        if result.get("code") == 200:
            print(f"[OK] PushPlus 推送成功，流水号：{result.get('data')}")
            return True
        else:
            print(f"[ERROR] PushPlus 返回异常：{result}")
            return False
    except Exception as e:
        print(f"[ERROR] PushPlus 请求失败：{e}")
        return False

def main():
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        raise SystemExit("环境变量 PUSHPLUS_TOKEN 未设置")

    pushed_ids = load_state()
    print(f"[INFO] 已记录 {len(pushed_ids)} 条历史条目")

    articles = fetch_articles()
    print(f"[INFO] 页面共提取到 {len(articles)} 条有效条目")

    if len(articles) == 0:
        print("[WARNING] 没有提取到任何条目，可能网页结构变了。")
        return

    new_articles = [a for a in articles if a["id"] not in pushed_ids]
    
    if not new_articles:
        print("[INFO] 没有新内容，本次无需推送")
        return

    print(f"[INFO] 发现 {len(new_articles)} 条新条目，准备推送")
    
    ok = push_to_wechat(token, new_articles)
    if ok:
        pushed_ids.update(a["id"] for a in new_articles)
        save_state(pushed_ids)
        print("[INFO] 状态文件已更新")
    else:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
