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
TARGET_URL = "http://jhsjk.people.cn/result/88?else=501&form=701"
PUSHPLUS_URL = "https://www.pushplus.plus/send"
STATE_FILE = Path("pushed_ids.json")

# 强化请求头，伪装成真实浏览器，防止被拦截
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
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
    """抓取页面并提取标题与链接（优化版）"""
    print(f"[INFO] 正在请求网页: {TARGET_URL}")
    resp = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []
    seen_links = set()

    # 直接找所有的 a 标签，然后通过链接格式来过滤，这是最稳妥的
    for a_tag in soup.find_all("a", href=True):
        title = a_tag.get_text(strip=True)
        link = a_tag["href"].strip()

        # 补全相对链接
        if link.startswith("//"):
            link = "http:" + link
        elif link.startswith("/"):
            link = "http://jhsjk.people.cn" + link

        # 过滤规则：标题不能太短，链接必须包含 /article/ 或者 /n1/
        if len(title) < 5:
            continue
        if "jhsjk.people.cn" not in link:
            continue
        
        # 只保留真正的文章详情页链接特征
        if "/article/" not in link and "/n1/" not in link:
            continue

        if link in seen_links:
            continue

        seen_links.add(link)
        articles.append({"title": title, "link": link, "id": make_id(title, link)})

    # 为了防止抓到侧边栏的推荐文章，我们通常只取最前面的 15 条
    return articles[:15]

def push_to_wechat(token: str, new_articles: list) -> bool:
    if not new_articles:
        return True

    items_html = ""
    for idx, art in enumerate(new_articles, 1):
        items_html += f'<p>{idx}. <a href="{art["link"]}" target="_blank">{art["title"]}</a></p>\n'

    content = (
        f"<h3>人民网“习近平系列重要讲话数据库”有新内容</h3>\n"
        f"<p>共 {len(new_articles)} 条新条目：</p>\n"
        f"{items_html}\n"
        f"<hr>\n"
        f"<p style='color:#888;font-size:12px;'>抓取时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
    )

    payload = {
        "token": token,
        "title": f"重要讲话数据库更新 · {len(new_articles)} 条新内容",
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
