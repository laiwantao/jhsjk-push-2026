#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
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
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}
# =======================================


def load_state() -> set:
    """加载已推送条目标识集合"""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return set(data.get("pushed_ids", []))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_state(ids: set) -> None:
    """保存已推送条目标识集合（只保留最近 500 条，防止文件无限膨胀）"""
    ids_list = list(ids)[-500:]
    STATE_FILE.write_text(
        json.dumps({"pushed_ids": ids_list}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def make_id(title: str, link: str) -> str:
    """用标题 + 链接生成稳定标识，避免仅靠标题重复"""
    raw = f"{title.strip()}|{link.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def fetch_articles() -> list:
    """抓取页面并提取标题与链接"""
    resp = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding  # 人民网页面编码可能为 gb2312/gbk

    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    seen_links = set()

    for li in soup.find_all("li"):
        a_tag = li.find("a", href=True)
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        link = a_tag["href"].strip()

        # 补全相对链接
        if link.startswith("//"):
            link = "http:" + link
        elif link.startswith("/"):
            link = "http://jhsjk.people.cn" + link

        # 过滤：标题太短、链接不是文章详情页的跳过
        if len(title) < 5:
            continue
        if "jhsjk.people.cn" not in link:
            continue
        if link in seen_links:
            continue

        seen_links.add(link)
        articles.append({"title": title, "link": link, "id": make_id(title, link)})

    return articles


def push_to_wechat(token: str, new_articles: list) -> bool:
    """通过 PushPlus 推送新条目"""
    if not new_articles:
        print("[INFO] 没有新条目，跳过推送")
        return True

    # 构造 HTML 内容
    items_html = ""
    for idx, art in enumerate(new_articles, 1):
        items_html += (
            f'<p>{idx}. <a href="{art["link"]}" target="_blank">{art["title"]}</a></p>\n'
        )

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
    print(f"[INFO] 页面共提取到 {len(articles)} 条条目")

    # 筛选新条目（不在已推送集合中）
    new_articles = [a for a in articles if a["id"] not in pushed_ids]
    # 只取前 10 条避免单次推送过长
    new_articles = new_articles[:10]

    if not new_articles:
        print("[INFO] 没有新内容，本次无需推送")
        return

    print(f"[INFO] 发现 {len(new_articles)} 条新条目，准备推送")
    for a in new_articles:
        print(f"  - {a['title']}")

    ok = push_to_wechat(token, new_articles)
    if ok:
        pushed_ids.update(a["id"] for a in new_articles)
        save_state(pushed_ids)
        print("[INFO] 状态文件已更新")
    else:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
