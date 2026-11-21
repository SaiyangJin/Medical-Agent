"""临时脚本：合并分批抽取的疾病-症状数据，归一化后导入 Neo4j。

为什么不沿用旧逻辑：
  abstract_output.jsonl 是分批调用 LLM 产出的，同一个疾病可能被截断在两批里。
  旧代码用 dict 直接读 / 覆盖式处理，后一批会吃掉前一批的症状。
  这里改成：按疾病累积症状列表 -> 归一化 -> 按 (疾病, 症状) 去重 -> 批量写 Neo4j。

流程：
  1. 逐行读 JSONL，把同一疾病的所有症状追加到一起（不覆盖）
  2. 查全局同义映射表，把症状替换成标准词
  3. 按 (疾病, 归一化后的症状) 去重，保留第一条 quote
  4. 清空旧图谱后分批 MERGE

注意：CLEAR_FIRST=True 会删除 Neo4j 里的全部节点，再重新导入。

运行：
    uv run python -m src.data_graph.save_abstracted_v2
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src.data_graph.neo4j_init import neo4j_driver

ROOT = Path(__file__).resolve().parents[2]
ABSTRACT_OUTPUT_PATH = ROOT / "data" / "graph" / "abstract_output.jsonl"
SYNONYM_MAP_PATH = ROOT / "data" / "graph" / "symptom_synonym_map.json"

CLEAR_FIRST = True   # 数据整体换过，先清空旧图谱
BATCH_SIZE = 500


def load_merged() -> dict[str, list[tuple[str, str]]]:
    """按疾病累积症状；同一疾病出现在多个批次时，列表追加而不是覆盖。"""
    merged: dict[str, list[tuple[str, str]]] = defaultdict(list)

    lines = ABSTRACT_OUTPUT_PATH.read_text(encoding="utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        disease_map = record[0]
        for disease, symptoms in disease_map.items():
            if not disease:
                continue
            for item in symptoms:
                if not item:
                    continue
                symptom = (item[0] or "").strip()
                quote = item[1] if len(item) > 1 else ""
                if symptom:
                    merged[disease].append((symptom, quote))

    return merged


def main() -> None:
    synonym_map = json.loads(SYNONYM_MAP_PATH.read_text(encoding="utf-8"))
    merged = load_merged()

    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    raw_count = 0

    for disease, symptoms in merged.items():
        for symptom, quote in symptoms:
            raw_count += 1
            normalized = synonym_map.get(symptom, symptom)
            key = (disease, normalized)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"disease": disease, "symptom": normalized, "quote": quote})

    if CLEAR_FIRST:
        print("清空旧图谱...")
        neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")

    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i : i + BATCH_SIZE]
        neo4j_driver.execute_query(
            """
            UNWIND $rows AS row
            MERGE (d:DISEASE {name: row.disease})
            MERGE (s:SYMPTOM {name: row.symptom})
            MERGE (d)-[p:HAS_SYMPTOM]->(s)
            SET p.quote = row.quote
            """,
            rows=chunk,
        )
        print(f"  写入 {min(i + BATCH_SIZE, len(rows))}/{len(rows)}")

    d = neo4j_driver.execute_query("MATCH (d:DISEASE) RETURN count(d) AS c").records[0]["c"]
    s = neo4j_driver.execute_query("MATCH (s:SYMPTOM) RETURN count(s) AS c").records[0]["c"]
    r = neo4j_driver.execute_query(
        "MATCH ()-[p:HAS_SYMPTOM]->() RETURN count(p) AS c"
    ).records[0]["c"]

    print("\n[OK]")
    print(f"  疾病数: {len(merged)} -> 写入 {d}")
    print(f"  原始症状记录: {raw_count}")
    print(f"  归一化+去重后: {len(rows)}")
    print(f"  图谱概念数: {len(set(x['symptom'] for x in rows))} -> 写入 {s}")
    print(f"  关系数: {r}")


if __name__ == "__main__":
    main()
