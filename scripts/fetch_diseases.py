"""阶段 0.1 — 从 Wikidata 枚举中文维基的疾病条目。

产出 data/raw/diseases.json，形如：
    [{"qid": "Q1472", "label": "克隆氏症", "title": "克隆氏症"}, ...]

运行：
    uv run python scripts/fetch_diseases.py
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import _common

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
PAGE_SIZE = 300

# wdt:P31/wdt:P279* = "instance of" 及其全部子类，起点 wd:Q12136 即 disease。
# schema:about + isPartOf 用于筛出"在中文维基有独立条目"的疾病——没有条目就没有正文可抓。
# 注意：字符串里出现字面花括号要写成 {{ }}，否则 str.format 会把它们当占位符。
QUERY = """
SELECT DISTINCT ?d ?dLabel ?article WHERE {{
  ?d wdt:P31/wdt:P279* wd:Q12136 .
  ?article schema:about ?d ;
           schema:isPartOf <https://zh.wikipedia.org/> .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,zh-hans,zh-hant,en". }}
}}
ORDER BY ?d
LIMIT {limit} OFFSET {offset}
"""

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "diseases.json"


def to_rows(payload: dict) -> list[dict]:
    """把 SPARQL 的嵌套 JSON 摊平成 {qid, label, title} 列表。"""
    rows = []
    for b in payload["results"]["bindings"]:
        rows.append(
            {
                "qid": b["d"]["value"].rsplit("/", 1)[-1],
                "label": b.get("dLabel", {}).get("value", ""),
                # 条目 URL 里的标题是 percent-encoded，下划线需还原成空格
                "title": urllib.parse.unquote(
                    b["article"]["value"].split("/wiki/", 1)[-1]
                ).replace("_", " "),
            }
        )
    return rows


def main() -> None:
    _common.setup_stdout()

    # dict 在此当有序集合用：key 是 qid，天然去重
    seen: dict[str, dict] = {}
    with _common.make_client() as client:
        offset = 0
        while True:
            print(f"[SPARQL] offset={offset}")
            resp = _common.fetch(
                client,
                SPARQL_ENDPOINT,
                params={"query": QUERY.format(limit=PAGE_SIZE, offset=offset), "format": "json"},
                headers={"Accept": "application/sparql-results+json"},
            )
            rows = to_rows(resp.json())
            if not rows:
                break
            for r in rows:
                seen.setdefault(r["qid"], r)
            if len(rows) < PAGE_SIZE:  # 最后一页不满，说明取完了
                break
            offset += PAGE_SIZE

    result = sorted(seen.values(), key=lambda r: r["qid"])
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 共 {len(result)} 个疾病 -> {OUT_PATH}")


if __name__ == "__main__":
    main()
