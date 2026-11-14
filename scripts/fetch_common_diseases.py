"""阶段 0.1（常见病版）— 按页面浏览量筛选中文维基的常见疾病条目。

产出 data/raw/diseases.json，格式与 fetch_diseases.py 一致：
    [{"qid": "Q12206", "label": "糖尿病", "title": "糖尿病"}, ...]

流程：
  1. 读取 Category:疾病 的直接成员，取其中 21 个 ICD-10 章节页 + 疾病列表页
  2. 解析这些页面的 [[链接]]，作为候选疾病标题
  3. 分批查询最近 30 天页面浏览量
  4. 按浏览量降序取前 TOP_N 个
  5. 分批查询对应的 Wikidata qid

为什么这么做：原版从 Wikidata 全量枚举「疾病及其子类」，结果里冷门病占绝大多数，
糖尿病/高血压/肺癌这类常见病反而缺失。中文维基的页面浏览量能直接反映「这个病有
多常见」，按它降序取前 N 个就是用户真正关心的病。

为什么不递归分类树：Category:疾病 的子树有几百个子分类，MediaWiki API 会持续
返回 429，跑完要几个小时。ICD-10 章节页已经把疾病按系统组织好了，一次请求一个
页面就能拿到几十到上百个链接，请求数从 400+ 降到 ~100。

运行：
    uv run python scripts/fetch_common_diseases.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import _common

API = "https://zh.wikipedia.org/w/api.php"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT_PATH = RAW_DIR / "diseases.json"

ROOT_CATEGORY = "Category:疾病"
EXTRA_PAGES = ["疾病列表"]
TOP_N = 679           # 与原 raw 数据量一致
BATCH = 50            # MediaWiki titles 参数上限
SLEEP = 0.5           # 礼貌间隔（0.2s 实测容易触发 429）

LINK_RE = re.compile(r"\[\[([^\]|#]+)")
# 所有以 "*" 开头的行都算条目行，兼容两种格式：
#   * I00 [[风湿热]]
#   * ({{ICD10|E|00||e|00}}) [[先天性碘缺乏综合征]]
# 章节标题行不以 "*" 开头，所以天然避开了解剖/系统名的链接。
BULLET_RE = re.compile(r"^\*.*$", re.M)

# 兜底过滤：即使出现在条目行里，这些也不是疾病条目
NON_DISEASE_TITLES = {
    "大麻", "可卡因", "酒精", "烟草", "阿片", "地震",
    "眼", "耳", "鼻", "口", "脑", "尿", "血", "玻璃", "蜥蜴", "黄蜂",
    "消化系统", "自主神经系统", "三叉神经", "动脉", "静脉", "毛细血管",
    "尿道", "小肠", "晶状体", "踝", "甲状腺", "卵巢", "睾丸", "内分泌腺",
    "胸腺", "垂体", "肾上腺", "胃", "肠", "肺", "肝", "肾", "脾", "心",
}

# 页面分类里出现这些关键词，才认为该页面是疾病/症状条目。
# 用于过滤 ICD-10 页面里混入的解剖部位、外因、物质等（手、胸、洪水、石棉……）。
DISEASE_CAT_KEYWORDS = (
    "疾病", "症", "病", "癌", "肿瘤", "炎", "感染", "障碍",
    "损伤", "中毒", "畸形", "缺损", "不全", "紊乱", "失调",
)


def api_get(client, params: dict) -> dict:
    resp = _common.fetch(client, API, params={**params, "format": "json"})
    return resp.json()


def category_members(client, cat: str) -> list[str]:
    out: list[str] = []
    cont: dict = {}
    while True:
        data = api_get(
            client,
            {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": cat,
                "cmnamespace": "0",
                "cmlimit": "500",
                **cont,
            },
        )
        out.extend(m["title"] for m in data.get("query", {}).get("categorymembers", []))
        cont = data.get("continue", {})
        if not cont:
            break
        time.sleep(SLEEP)
    return out


def subcategories(client, cat: str) -> list[str]:
    """只取直接子分类（ns=14），不递归。"""
    out: list[str] = []
    cont: dict = {}
    while True:
        data = api_get(
            client,
            {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": cat,
                "cmnamespace": "14",
                "cmlimit": "500",
                **cont,
            },
        )
        out.extend(m["title"] for m in data.get("query", {}).get("categorymembers", []))
        cont = data.get("continue", {})
        if not cont:
            break
        time.sleep(SLEEP)
    return out


def page_wikitext(client, page: str) -> str:
    data = api_get(client, {"action": "parse", "page": page, "prop": "wikitext"})
    return data.get("parse", {}).get("wikitext", {}).get("*", "")


def parse_icd_links(text: str) -> list[str]:
    """只取列表行（以 * 开头）里的链接，避开章节标题里的解剖/系统名。"""
    out: list[str] = []
    for line in BULLET_RE.findall(text):
        out.extend(x.strip() for x in LINK_RE.findall(line) if x.strip())
    return out


def collect_titles(client) -> list[str]:
    print("  读取 Category:疾病 直接成员")
    members = category_members(client, ROOT_CATEGORY)
    print(f"    直接成员 {len(members)} 个")

    subcats = subcategories(client, ROOT_CATEGORY)
    print(f"  直接子分类 {len(subcats)} 个")

    titles: set[str] = set(members)
    for cat in subcats:
        try:
            memo = category_members(client, cat)
        except Exception as exc:
            print(f"    [WARN] {cat}: {type(exc).__name__}")
            continue
        titles.update(memo)
        print(f"    {cat}: +{len(memo)}，累计 {len(titles)}")
        time.sleep(SLEEP)

    icd_pages = [t for t in members if t.startswith("ICD-10")]
    print(f"  ICD-10 章节页 {len(icd_pages)} 个，补充页 {EXTRA_PAGES}")
    for page in icd_pages:
        try:
            text = page_wikitext(client, page)
        except Exception as exc:
            print(f"    [WARN] {page}: {type(exc).__name__}")
            continue
        links = parse_icd_links(text)
        titles.update(links)
        print(f"    {page}: +{len(links)} 个链接")
        time.sleep(SLEEP)

    for page in EXTRA_PAGES:
        try:
            text = page_wikitext(client, page)
        except Exception as exc:
            print(f"    [WARN] {page}: {type(exc).__name__}")
            continue
        links = [x.strip() for x in LINK_RE.findall(text) if x.strip()]
        titles.update(links)
        print(f"    {page}: +{len(links)} 个链接")
        time.sleep(SLEEP)

    return sorted(titles)


def _clean_titles(titles: list[str]) -> list[str]:
    """`|` 是 titles 参数的分隔符，标题里含它会破坏批量查询。"""
    return [t for t in titles if "|" not in t]


def batch_pageviews(client, titles: list[str]) -> dict[str, int]:
    scores: dict[str, int] = {}
    titles = _clean_titles(titles)
    for i in range(0, len(titles), BATCH):
        chunk = titles[i : i + BATCH]
        data = api_get(
            client,
            {
                "action": "query",
                "titles": "|".join(chunk),
                "prop": "pageviews",
                "pvipdays": 30,
            },
        )
        for page in data.get("query", {}).get("pages", {}).values():
            pv = page.get("pageviews") or {}
            scores[page["title"]] = sum(v for v in pv.values() if isinstance(v, int))
        if i % 500 == 0:
            print(f"    pageviews {min(i + BATCH, len(titles))}/{len(titles)}")
        time.sleep(SLEEP)
    return scores


def batch_qids(client, titles: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    titles = _clean_titles(titles)
    for i in range(0, len(titles), BATCH):
        chunk = titles[i : i + BATCH]
        data = api_get(
            client,
            {
                "action": "query",
                "titles": "|".join(chunk),
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "redirects": "1",
            },
        )
        query = data.get("query", {})
        by_title: dict[str, str] = {}
        for page in query.get("pages", {}).values():
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                by_title[page["title"]] = qid
        # 繁简重定向页本身没有 wikibase_item，映射到目标页的 qid
        for r in query.get("redirects", []):
            if r["to"] in by_title:
                by_title[r["from"]] = by_title[r["to"]]
        result.update(by_title)
        time.sleep(SLEEP)
    return result


def filter_by_disease_category(client, titles: list[str]) -> list[str]:
    """只保留分类里带疾病关键词的页面，过滤解剖部位/外因/物质等噪音。"""
    kept: list[str] = []
    titles = _clean_titles(titles)
    for i in range(0, len(titles), BATCH):
        chunk = titles[i : i + BATCH]
        page_cats: dict[str, list[str]] = {}
        cont: dict = {}
        while True:
            data = api_get(
                client,
                {
                    "action": "query",
                    "titles": "|".join(chunk),
                    "prop": "categories",
                    "cllimit": "500",
                    **cont,
                },
            )
            for page in data.get("query", {}).get("pages", {}).values():
                page_cats.setdefault(page["title"], []).extend(
                    c["title"] for c in page.get("categories", [])
                )
            cont = data.get("continue", {})
            if not cont:
                break
            time.sleep(SLEEP)

        for t in chunk:
            cats = page_cats.get(t, [])
            if any(k in c for c in cats for k in DISEASE_CAT_KEYWORDS):
                kept.append(t)
        if i % 200 == 0:
            print(f"    分类过滤 {min(i + BATCH, len(titles))}/{len(titles)}，保留 {len(kept)}")
        time.sleep(SLEEP)

    return kept


def main() -> None:
    _common.setup_stdout()

    with _common.make_client(timeout=60) as client:
        print("[1/4] 收集候选标题")
        titles = collect_titles(client)
        print(f"  候选 {len(titles)} 个")

        print("[2/4] 查询最近 30 天页面浏览量")
        scores = batch_pageviews(client, titles)
        print(f"  拿到浏览量数据 {len(scores)} 个")
        if not scores:
            raise RuntimeError("没有拿到任何浏览量数据")

        print(f"[3/5] 按浏览量排序，取前 {TOP_N * 2} 做候选")
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: TOP_N * 2]
        shortlist = [t for t, _ in ranked]

        print("[4/5] 用页面分类过滤非疾病条目")
        disease_titles = filter_by_disease_category(client, shortlist)
        print(f"  保留 {len(disease_titles)} 个疾病条目")

        print(f"[5/5] 取前 {TOP_N}，查询 Wikidata qid")
        top_titles = disease_titles[:TOP_N]
        qids = batch_qids(client, top_titles)

    rows = [{"qid": qids[t], "label": t, "title": t} for t in top_titles if t in qids]
    bad_prefix = ("ICD-10", "疾病列表", "疾病分类", "Category:")
    rows = [
        r
        for r in rows
        if not r["title"].startswith(bad_prefix)
        and r["title"] != "疾病"
        and r["title"] not in NON_DISEASE_TITLES
    ]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[OK] {len(rows)} 条 -> {OUT_PATH}")
    print("Top 20:", "、".join(r["title"] for r in rows[:20]))


if __name__ == "__main__":
    main()
