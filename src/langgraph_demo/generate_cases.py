import json
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "data" / "cleaned" / "full.jsonl"
TARGET_PATH = ROOT / "data" / "test" / "cases.jsonl"

def process_full_jsonl(input_path: Path, output_path: Path):
    count = 0
    processed = 0

    with open(input_path, "r", encoding="utf-8") as fin, \
            open(output_path, "w", encoding="utf-8") as fout:

        for line in fin:
            line = line.strip()
            if not line:
                continue

            # 先递增计数器，再判断是否等于3
            count += 1

            if count == 8:
                try:
                    data = json.loads(line)
                    disease = data.get("disease", "").strip()

                    # 跳过疾病名为空的脏数据
                    if not disease:
                        print(f"[SKIP] 第 {processed + 1} 条目标数据 disease 为空，已跳过")
                        count = 0
                        continue

                    record = {
                        "question": f"{disease}怎么治疗",
                        "expect": "normal",
                        "expect_disease": disease
                    }

                    fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                    processed += 1
                    print(f"[OK] 已处理 {processed} 条 | disease: {disease}")

                except json.JSONDecodeError as e:
                    print(f"[ERROR] JSON 解析失败: {e}")

                # 处理完当前条后，计数器清零
                count = 0

            # count != 8 时，自动跳过，继续读取下一条

    print(f"\n✅ 完成！共处理 {processed} 条数据，输出文件: {output_path}")


if __name__ == "__main__":
    process_full_jsonl(SOURCE_PATH, TARGET_PATH)