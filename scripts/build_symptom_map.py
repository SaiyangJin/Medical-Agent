"""把分批抽取产生的局部症状同义表，合并成一张全局映射表。

输入 data/graph/abstract_output.jsonl
  每行：[疾病->症状列表, 局部同义映射 {标准词: [同义词...]}]

输出 data/graph/symptom_synonym_map.json
  {"原词": "标准词", ...}  —— 只包含"需要替换"的词

合并策略：
  1. 每个 (标准词, 同义词) 当成一条边，用并查集把所有相关词连成一个连通分量
  2. 每个连通分量选一个代表词：优先选被当标准词次数最多的，其次最短的
  3. 这样跨批次的分歧（A 批叫"乏力"、B 批叫"疲劳"）会被合并到同一个标准词

运行：
    uv run python scripts/build_symptom_map.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "graph" / "abstract_output.jsonl"
OUT_PATH = ROOT / "data" / "graph" / "symptom_synonym_map.json"


def main() -> None:
    lines = [l for l in IN_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]

    std_count: Counter[str] = Counter()
    edges: list[tuple[str, str]] = []

    for line in lines:
        record = json.loads(line)
        mapping = record[1]
        for std, syns in mapping.items():
            std_count[std] += 1
            for syn in syns:
                edges.append((std, syn))

    # ---------- 并查集 ----------
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        # 路径压缩
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in edges:
        union(a, b)

    # ---------- 分组并选代表 ----------
    groups: dict[str, list[str]] = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)

    def pick_representative(words: list[str]) -> str:
        # 频次高优先，其次短词优先，再按字典序保证结果稳定
        return min(words, key=lambda w: (-std_count.get(w, 0), len(w), w))

    mapping: dict[str, str] = {}
    representatives: set[str] = set()
    for words in groups.values():
        rep = pick_representative(words)
        representatives.add(rep)
        for w in words:
            if w != rep:
                mapping[w] = rep

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(dict(sorted(mapping.items())), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ---------- 汇报 ----------
    print(f"输入记录: {len(lines)}")
    print(f"原始词条: {len(parent)}（标准词 {len(std_count)} + 同义词）")
    print(f"合并后概念数: {len(representatives)}")
    print(f"需要替换的词: {len(mapping)}")
    print(f"输出: {OUT_PATH}")

    # 抽查几个冲突合并的结果
    samples = ["乏力", "疲劳", "高烧", "高热", "发烧", "发热", "食欲不振", "食欲减退"]
    for s in samples:
        if s in parent:
            print(f"  {s} -> {find(s)}")


if __name__ == "__main__":
    main()
