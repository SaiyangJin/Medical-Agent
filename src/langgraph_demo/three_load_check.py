from content_retrieve_graph import retrieve_by_keyword,retrieve_by_embedding,retrieve_by_knowledge_graph
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from rich.table import Table
from rich.text import Text
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "test"
SOURCE_PATH = RAW_DIR / "cases_score.jsonl"

console = Console()

def one_test(question:str):
    # question = json.loads(line)["question"]
    graph_res = retrieve_by_knowledge_graph(
        question)
    graph_res.sort(key=lambda one: one["score"])
    embed_res = retrieve_by_embedding(
        question)
    embed_res.sort(key=lambda one: one["score"])
    keyword_res = retrieve_by_keyword(
        question)
    keyword_res.sort(key=lambda one: one["score"])

    # 1. 确定当前偏向路线及主题色

    # 2. 构建非表格化的召回详情
    detail_lines = []
    routes_config = [
        ("🕸️ 知识图谱", graph_res, "bright_magenta"),
        ("🧠 向量检索", embed_res, "bright_cyan"),
        ("🔑 关键词", keyword_res, "bright_yellow"),
    ]

    for name, res_list, color in routes_config:
        # 路线标题：如果是当前偏向路线，则高亮并加标记
        detail_lines.append(Text(name+"路线:",style=color))
        # 逐条展示 Top5，使用缩进代替表格列
        if not res_list:
            detail_lines.append(Text("   (无召回结果)", style="dim italic"))
        else:
            for i, r in enumerate(res_list[:5], 1):
                score = r['score']
                # 分数根据高低动态着色，直观反映质量
                if score > 0.35:
                    score_style = "dim red"
                elif score > 0.25:
                    score_style = "bright_blue"
                else:
                    score_style = "bold bright_green"

                line = Text.assemble(
                    (f"   {i}. ", "dim"),
                    (f"[{r['disease']}][{r['title']}]", color),
                    ("  ⟫  ", "dim"),
                    (f"{score:.4f}", score_style)
                )
                detail_lines.append(line)

        detail_lines.append(Text(""))  # 路线间空行分隔

    # 3. 组装最终面板
    header = Text.assemble(
        ("❓ ", "bold white"),
        (question, "bold bright_white"),
    )

    console.print(header)
    console.print(*detail_lines, sep="\n")


def all_tests():
    # 打开cases_score文件，读取里面的line的question
    with open(SOURCE_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
        count = 0
        for line in lines:
            question = json.loads(line)["question"]
            graph_res = retrieve_by_knowledge_graph(
                question)
            graph_res.sort(key=lambda one: one["score"])
            embed_res = retrieve_by_embedding(
                question)
            embed_res.sort(key=lambda one: one["score"])
            keyword_res = retrieve_by_keyword(
                question)
            keyword_res.sort(key=lambda one: one["score"])

            # 1. 确定当前偏向路线及主题色
            if 0 <= count < 20:
                route_label, theme_color = "向量检索路线", "bright_cyan"
            elif 20 <= count < 40:
                route_label, theme_color = "关键词检索路线", "bright_yellow"
            elif 40 <= count < 60:
                route_label, theme_color = "知识图谱路线", "bright_magenta"
            else:
                route_label, theme_color = "综合路线", "bright_green"

            # 2. 构建非表格化的召回详情
            detail_lines = []
            routes_config = [
                ("🕸️ 知识图谱", graph_res, "bright_magenta"),
                ("🧠 向量检索", embed_res, "bright_cyan"),
                ("🔑 关键词", keyword_res, "bright_yellow"),
            ]

            for name, res_list, color in routes_config:
                # 路线标题：如果是当前偏向路线，则高亮并加标记
                is_target = name.replace("🕸️ ", "").replace("🧠 ", "").replace("🔑 ", "") in route_label
                title_style = f"bold {color} underline" if is_target else f"dim {color}"
                marker = " ◀ 偏向" if is_target else ""

                detail_lines.append(Text(f"{name}{marker}", style=title_style))

                # 逐条展示 Top5，使用缩进代替表格列
                if not res_list:
                    detail_lines.append(Text("   (无召回结果)", style="dim italic"))
                else:
                    for i, r in enumerate(res_list[:5], 1):
                        score = r['score']
                        # 分数根据高低动态着色，直观反映质量
                        if score > 0.35:
                            score_style = "dim red"
                        elif score > 0.25:
                            score_style = "bright_blue"
                        else:
                            score_style = "bold bright_green"

                        line = Text.assemble(
                            (f"   {i}. ", "dim"),
                            (f"[{r['disease']}][{r['title']}]", color),
                            ("  ⟫  ", "dim"),
                            (f"{score:.4f}", score_style)
                        )
                        detail_lines.append(line)

                detail_lines.append(Text(""))  # 路线间空行分隔

            # 3. 组装最终面板
            header = Text.assemble(
                ("❓ ", "bold white"),
                (question, "bold bright_white"),
            )

            console.print(Rule(style=theme_color))
            console.print(header)
            console.print(Text(f"🎯 评估倾向: {route_label}", style=f"bold {theme_color}"))
            console.print(*detail_lines, sep="\n")

            count += 1


if __name__ == '__main__':
    # question = "患者无法正常辨别某些颜色，最常见的是红绿色觉异常。多数为先天性遗传，因视锥细胞中的感光色素缺失或功能异常所致，男性发病率显著高于女性"
    # test_all()
    # one_test("我有点拉肚子，最近几天还天天睡不着，感到心慌，这怎么回事？")
    one_test("我有点拉肚子，肚子还一阵一阵地绞着疼，拉完总觉得没排干净，最近几天天天睡不着，就算睡着了也全是梦、稍微有点动静就醒，白天头晕乎乎的没精神，脑子像蒙了层雾似的转不动，感到心慌，心里突突跳得厉害，手心脚心老冒汗，稍微动一下就喘不上气，嘴里还发干发苦，吃什么都没胃口，这怎么回事")
    # one_test("我有点腹泻，伴阵发性腹部绞痛及排便不尽感，最近几天天天失眠，伴多梦、睡眠浅易觉醒，日间存在头晕、乏力及脑雾样认知迟钝表现，感到心悸，自觉心动过速明显，伴手足多汗、劳力性气短、口干口苦及食欲减退症状，这怎么回事？")




