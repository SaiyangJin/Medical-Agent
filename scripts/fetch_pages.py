"""阶段 0.2 — 抓取疾病条目的 wikitext 正文。

输入  data/raw/diseases.json
输出  data/raw/pages.jsonl   （每行一条 JSON，含完整 wikitext）

支持断点续跑：重跑时自动跳过 pages.jsonl 里已完成的 qid，中断不丢进度。

运行：
    uv run python scripts/fetch_pages.py
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path

import _common

# 两个端点内容等价，但可达性与限流额度各自独立。
# 脚本轮流使用它们 —— 相当于把可用额度翻倍。
API_ENDPOINTS = [
    "https://api.wikimedia.org/core/v1/wikipedia/zh/page/{title}",
    "https://zh.wikipedia.org/w/rest.php/v1/page/{title}",
]

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
IN_PATH = RAW_DIR / "diseases.json"
OUT_PATH = RAW_DIR / "pages.jsonl"
FAIL_PATH = RAW_DIR / "fetch_failures.json"

# 维基匿名 API 的限流阈值很低（实测连续约 28 次就开始返 429）。
# 2 秒间隔 ≈ 679 条跑 25 分钟，是"能跑完"和"不惹恼服务端"之间的平衡点。
DELAY = 2.0
MAX_REDIRECTS = 5  # 防重定向环

# 中文维基大量条目是繁简重定向，例如「高血压」#REDIRECT [[高血壓]]。
# 不跟随的话会抓回一个 26 字符的空壳。
REDIRECT_RE = re.compile(r"#\s*redirect\s*:?\s*\[\[([^\]|#]+)", re.IGNORECASE)


def load_done() -> set[str]:
    """读已存在的 jsonl，返回已完成 qid 集合，用于断点续跑。"""
    if not OUT_PATH.exists():
        return set()
    done: set[str] = set()
    with OUT_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["qid"])
            except (json.JSONDecodeError, KeyError):
                continue  # 上次写到一半的残行，跳过
    return done


# 记录下一次该从哪个端点起手，实现"轮流使用"
_endpoint_counter = 0

# 各端点的连续失败次数：连着挂几次就暂时不用它，免得每次都白等一轮
_endpoint_fails: dict[str, int] = {}
FAIL_THRESHOLD = 3


def _alive_endpoints() -> list[str]:
    """挑出没被熔断的端点；全熔断了就重置（那是整体网络问题，怪端点没用）。"""
    alive = [t for t in API_ENDPOINTS if _endpoint_fails.get(t, 0) < FAIL_THRESHOLD]
    if alive:
        return alive
    _endpoint_fails.clear()
    return list(API_ENDPOINTS)


def fetch_json(client, title: str, retries: int = 2) -> dict:
    """轮流使用可用端点，任一个失败就顺延到下一个。

    两个域名的可达性和限流额度都是独立的——本机实测过「一个通、另一个断」。
    轮流起手让额度翻倍；连续挂掉的端点会被暂时熔断，避免每次白等。
    """
    global _endpoint_counter
    alive = _alive_endpoints()
    start = _endpoint_counter % len(alive)
    _endpoint_counter += 1

    last: Exception | None = None
    for offset in range(len(alive)):
        tmpl = alive[(start + offset) % len(alive)]
        url = tmpl.format(title=urllib.parse.quote(title, safe=""))
        try:
            resp = _common.fetch(
                client, url, headers={"Accept": "application/json"}, retries=retries
            )
            _endpoint_fails[tmpl] = 0  # 一次性成功就清零
            return resp.json()
        except Exception as exc:
            _endpoint_fails[tmpl] = _endpoint_fails.get(tmpl, 0) + 1
            last = exc
            print(f"    {url.split('/')[2]} 失败（{type(exc).__name__}）")
    raise RuntimeError("所有可用端点均失败") from last


def get_page(client, title: str, depth: int = 0) -> dict:
    """取一个条目的 wikitext，自动跟随繁简重定向。"""
    data = fetch_json(client, title)

    source = data.get("source", "")
    m = REDIRECT_RE.match(source.strip())
    if m and depth < MAX_REDIRECTS:
        return get_page(client, m.group(1).strip(), depth + 1)

    return {
        "title": title,
        "resolved_title": data.get("title", title),
        "pageid": data.get("id"),
        "revision": (data.get("latest") or {}).get("id"),  # 记版本号，保证可复现
        "wikitext": source,
        "length": len(source),
    }


def main() -> None:
    _common.setup_stdout()

    diseases = json.loads(IN_PATH.read_text(encoding="utf-8"))
    done = load_done()
    todo = [d for d in diseases if d["qid"] not in done]
    print(f"总计 {len(diseases)}  已完成 {len(done)}  本次待抓 {len(todo)}")
    if not todo:
        print("没有待抓的条目，已全部完成。")
        return

    failed: list[dict] = []
    started = time.time()
    with _common.make_client(timeout=60) as client, OUT_PATH.open("a", encoding="utf-8") as out:
        for i, d in enumerate(todo, 1):
            try:
                page = get_page(client, d["title"])
            except Exception as exc:
                failed.append(
                    {"qid": d["qid"], "title": d["title"], "error": f"{type(exc).__name__}: {exc}"}
                )
                print(f"  [FAIL] {d['title']} — {type(exc).__name__}")
                continue

            out.write(
                json.dumps({"qid": d["qid"], "label": d["label"], **page}, ensure_ascii=False) + "\n"
            )
            out.flush()  # 立即落盘，随时中断都不丢

            if i % 20 == 0 or i == len(todo):
                elapsed = time.time() - started
                eta = elapsed / i * (len(todo) - i)
                print(
                    f"  进度 {i}/{len(todo)}  "
                    f"已用 {elapsed / 60:.1f} 分钟  "
                    f"预计还需 {eta / 60:.1f} 分钟"
                )
            time.sleep(DELAY)

    print(f"[OK] 本次新增 {len(todo) - len(failed)} 条 -> {OUT_PATH}")
    if failed:
        FAIL_PATH.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[WARN] {len(failed)} 条失败 -> {FAIL_PATH}（直接重跑本脚本即可补抓）")


if __name__ == "__main__":
    main()
