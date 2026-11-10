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

# 🔥 关键修改：完全伪装成苹果手机浏览器，降低被封概率
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
    resp = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding

    # 🔥 诊断功能：如果抓不到东西，把网页前 100 个字符打印出来，看看是不是被拦截了
    print(f"[DEBUG] 网页开头内容: {resp.text[:100].strip()}")

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []
    seen_links = set()

    for a_tag in soup.find_all("a", href=True):
        title = a_tag.get_text(strip=True)
        link = a_tag["href"].strip()

        if link.startswith("//"):
            link = "http:" + link
        elif link.startswith("/"):
            link = "http://jhsjk.people.cn" + link

        if len(title) < 5:
            continue
        if "jhsjk.people.cn" not in link:
            continue
        if "/article/" not in link and "/n1/" not in link:
            continue

        if link in seen_links:
            continue

        seen_links.add(link)
        articles.append({"title": title, "link": link, "id": make_id(title, link)})

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
    print(f"[INFO] 页面共提取到 {len(articles)} 条条目")

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
