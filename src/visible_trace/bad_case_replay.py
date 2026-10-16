#测试bad-case回放逻辑
from typing import Any, Sequence

from click import style

from src.parent_child_chunk.init_model import engine
from src.langgraph_demo.trace_table_init import trace_table,request_table
from sqlalchemy import select
from rich.text import Text
from rich.console import Console
from rich.table import Table,Column,Row
from rich.panel import Panel
from rich.prompt import Prompt
console = Console()


def short(value, indent=0) -> Text:
    pad = "  " * indent
    #Text存片段列表，供打印
    t = Text()

    if isinstance(value, str):
        if len(value) <= 60:
            #这边style=green，自动帮我们拼贴
            t.append(value, style="green")
        else:
            t.append(value[:60], style="green")
            t.append(f"...(剩余{len(value) - 60}字)", style="dim")
        return t

    if isinstance(value, (int, float, bool)) or value is None:
        #处理None值1
        3
        3
        t.append(str(value), style="dim" if value is None else "yellow")
        return t

    if isinstance(value, list):
        t.append("[", style="dim")
        for idx, item in enumerate(value[:2]):
            if idx > 0:
                t.append(", ", style="dim")
            t.append_text(short(item, indent + 1))
        if len(value) > 2:
            t.append(f", ...还有{len(value) - 2}项", style="dim")
        t.append("]", style="dim")
        return t

    # ---- 字典 ----
    if isinstance(value, dict):
        if not value:
            t.append("{}", style="dim")
            return t

        t.append("{\n", style="dim")
        items = list(value.items())
        for idx, (k, v) in enumerate(items):
            t.append("  " * (indent + 1))
            t.append(str(k), style="cyan")
            t.append(" : ", style="dim")
            t.append_text(short(v, indent + 1))
            if idx < len(items) - 1:
                t.append(",", style="dim")
            t.append("\n", style="dim")
        t.append(pad + "}", style="dim")
        return t

    return Text(str(value))


#重播函数,传入trace_id，打印本次调用完整的链路
def print_one_request_trace(trace_id:str):
    text = Text()
    #1，根据trace_id，按照时间排序，获取调用的顺序
    with engine.begin() as conn:
        res = conn.execute(
            select(trace_table).where(trace_table.c.trace_id == trace_id).order_by(trace_table.c.start_time)).all()
    #2.0打印调用总信息
    if not res:
        console.print("没有找到该trace_id的数据")
        return
    text.append("====【总信息】====\n")
    text.append("问题: ")
    text.append(res[0]._mapping["question"],style="blue")
    text.append("\n")
    text.append("trace_id: ")
    text.append(trace_id,style="blue")
    text.append("\n")


    for index,re in enumerate(res):


        #2.1，打印节点名称
        text+=f"\n----[节点执行次序:{index}]----\n"
        # 2.2,如果有错误打印出来
        if re._mapping["error"]:
            text.append("❌️错误信息: ")
            text.append(re._mapping["error"],style="red")
            text.append("\n")
        text.append("节点名称: ")
        text.append(re._mapping["node_name"],style="blue")
        text.append("\n")
        #2.3,打印节点结果
        text.append("节点结果: ")
        text.append_text(short(re._mapping["result"]))
        text.append("\n")
        #2.4打印开始时间，结束时间，花费时间
        text.append("开始时间: ")
        text.append(str(re._mapping["start_time"]),style="blue")
        text.append("\n")
        text.append("结束时间: ")
        text.append(str(re._mapping["end_time"]),style="blue")
        text.append("\n")
        text.append("花费时间: ")
        text.append(str(re._mapping["cost_time"]),style="blue")
        text.append("秒\n")

    console.print(text)

    while True:
        #按任意键继续
        console.print("按任意键继续(可能有下一条请求)...")
        console.input()
        break

#打印所有不过请求的链路
#传入一个run_id

def get_recently_run_id()->str:
    with (engine.begin() as conn):
        return conn.execute(select(request_table.c.run_id)
                              .order_by(request_table.c.create_time.desc())
                              #默认升序，需要降序，取最新的
                              .limit(1)).scalar()

def print_all_not_passed_request(run_id:str):
    #2.3.1，先找到最近一次run_id的所有评测数据
    with (engine.begin() as conn):
        pre_sql = select(request_table).where(request_table.c.run_id == run_id,request_table.c.passed==False)
        execute_res_all = conn.execute(pre_sql).all()
    #2.3.2找到not-passed的数据，打印出不过理由，然后是整条链路的打印
    #一个请求用表格类型打印吧。
    for index,res in enumerate(execute_res_all):
        #此处打印出本条请求数据数据的类型type，passed，is_system_error(如果是要变红),对应的trace_id,run_id,citation_status引用状态
        #还有失败理由fail_reason,create_time，end_time，cost_time，如果是normal类型还需要打印出rank就是期待病症在资料中的排名，
        console.rule(f"[bold]请求 {index + 1}[/bold]")

        # 两列、无表头、无边框 —— 就是干净的「字段名   值」
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim", justify="right")
        table.add_column()

        table.add_row("类型",     Text(str(res.type), style="cyan"))
        table.add_row("是否通过",  Text("✅ 通过" if res.passed else "❌ 失败",
                                        style="green" if res.passed else "bold red"))
        table.add_row("系统错误",  Text(str(res.is_system_error),
                                        style="red" if res.is_system_error else "dim"))
        table.add_row("引用状态",  Text(str(res.citation_status or "-"), style="cyan"))
        table.add_row("失败理由",  Text(str(res.fail_reason) if res.fail_reason else "-",
                                        style="red" if res.fail_reason else "dim"))
        table.add_row("追踪 ID",   Text(str(res.trace_id), style="blue"))
        table.add_row("批次 ID",   Text(str(res.run_id), style="blue"))
        table.add_row("创建时间",  Text(str(res.create_time), style="dim"))
        table.add_row("结束时间",  Text(str(res.end_time), style="dim"))
        table.add_row("耗时",     Text(f"{res.cost_time:.2f}s", style="yellow"))

        # 排名：只有 normal 类型才有意义
        if res.type == "normal":
            if res.rank is None or res.rank < 0:
                rank_cell = Text("资料中未检索到", style="dim")
            elif res.rank <= 4:
                rank_cell = Text(f"第 {res.rank + 1} 位 ✅", style="green")
            else:
                rank_cell = Text(f"第 {res.rank + 1} 位 ❌", style="red")
        else:
            rank_cell = Text("—", style="dim")
        table.add_row("排名", rank_cell)

        if res.is_system_error:
            console.print(Panel(table, border_style="red", title="[bold red]⚠ 系统错误[/bold red]"))
        else:
            console.print(table)

        #打印详细信息
        console.print("以下是详细链路调用:\n")
        print_one_request_trace(str(res.trace_id))


def print_all_not_passed_system_error_request(run_id:str):
    #2.3.1，先找到最近一次run_id的所有评测数据
    with (engine.begin() as conn):
        pre_sql = select(request_table).where(request_table.c.run_id == run_id
                                              ,request_table.c.is_system_error==True
                                              ,request_table.c.passed==False)
        execute_res_all = conn.execute(pre_sql).all()
        print("有几条数据,", len(execute_res_all))
    #2.3.2找到not-passed的数据，打印出不过理由，然后是整条链路的打印
    #一个请求用表格类型打印吧。
    for index,res in enumerate(execute_res_all):
        #此处打印出本条请求数据数据的类型type，passed，is_system_error(如果是要变红),对应的trace_id,run_id,citation_status引用状态
        #还有失败理由fail_reason,create_time，end_time，cost_time，如果是normal类型还需要打印出rank就是期待病症在资料中的排名，
        console.rule(f"[bold]请求 {index + 1}[/bold]")

        # 两列、无表头、无边框 —— 就是干净的「字段名   值」
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim", justify="right")
        table.add_column()

        table.add_row("类型",     Text(str(res.type), style="cyan"))
        table.add_row("是否通过",  Text("✅ 通过" if res.passed else "❌ 失败",
                                        style="green" if res.passed else "bold red"))
        table.add_row("系统错误",  Text(str(res.is_system_error),
                                        style="red" if res.is_system_error else "dim"))
        table.add_row("引用状态",  Text(str(res.citation_status or "-"), style="cyan"))
        table.add_row("失败理由",  Text(str(res.fail_reason) if res.fail_reason else "-",
                                        style="red" if res.fail_reason else "dim"))
        table.add_row("追踪 ID",   Text(str(res.trace_id), style="blue"))
        table.add_row("批次 ID",   Text(str(res.run_id), style="blue"))
        table.add_row("创建时间",  Text(str(res.create_time), style="dim"))
        table.add_row("结束时间",  Text(str(res.end_time), style="dim"))
        table.add_row("耗时",     Text(f"{res.cost_time:.2f}s", style="yellow"))

        # 排名：只有 normal 类型才有意义
        if res.type == "normal":
            if res.rank is None or res.rank < 0:
                rank_cell = Text("", style="dim")
            elif res.rank <= 4:
                rank_cell = Text(f"第 {res.rank + 1} 位 ✅", style="green")
            else:
                rank_cell = Text(f"第 {res.rank + 1} 位 ❌", style="red")
        else:
            rank_cell = Text("—", style="dim")
        table.add_row("排名", rank_cell)

        if res.is_system_error:
            console.print(Panel(table, border_style="red", title="[bold red]⚠ 系统错误[/bold red]"))
        else:
            console.print(table)

        #打印详细信息
        console.print("以下是详细链路调用:\n")
        print_one_request_trace(str(res.trace_id))

def print_all_not_passed_not_system_error_request(run_id:str):
    #2.3.1，先找到最近一次run_id的所有评测数据
    with (engine.begin() as conn):
        pre_sql = select(request_table).where(request_table.c.run_id == run_id
                                              ,request_table.c.is_system_error==False
                                              ,request_table.c.passed==False)
        execute_res_all = conn.execute(pre_sql).all()
    if not execute_res_all:
        console.print("没有检索到任何信息")
    print_detail_info(execute_res_all)

def print_one_request(trace_id:str):
    #2.3.1，先找到最近一次run_id的所有评测数据
    with (engine.begin() as conn):
        execute_res_all = conn.execute(select(request_table).where(request_table.c.trace_id == trace_id)).all()
    if not execute_res_all:
        console.print("没有检索到任何信息")
    print_detail_info(execute_res_all)


def print_detail_info(execute_res_all):
    # 2.3.2找到not-passed的数据，打印出不过理由，然后是整条链路的打印
    # 一个请求用表格类型打印吧。
    for index, res in enumerate(execute_res_all):
        # 此处打印出本条请求数据数据的类型type，passed，is_system_error(如果是要变红),对应的trace_id,run_id,citation_status引用状态
        # 还有失败理由fail_reason,create_time，end_time，cost_time，如果是normal类型还需要打印出rank就是期待病症在资料中的排名，
        console.rule(f"[bold]请求 {index + 1}[/bold]")

        # 两列、无表头、无边框 —— 就是干净的「字段名   值」
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim", justify="right")
        table.add_column()

        table.add_row("类型", Text(str(res.type), style="cyan"))
        table.add_row("是否通过", Text("✅ 通过" if res.passed else "❌ 失败",
                                       style="green" if res.passed else "bold red"))
        table.add_row("系统错误", Text(str(res.is_system_error),
                                       style="red" if res.is_system_error else "dim"))
        table.add_row("引用状态", Text(str(res.citation_status or "-"), style="cyan"))
        table.add_row("失败理由", Text(str(res.fail_reason) if res.fail_reason else "-",
                                       style="red" if res.fail_reason else "dim"))
        table.add_row("追踪 ID", Text(str(res.trace_id), style="blue"))
        table.add_row("批次 ID", Text(str(res.run_id), style="blue"))
        table.add_row("创建时间", Text(str(res.create_time), style="dim"))
        table.add_row("结束时间", Text(str(res.end_time), style="dim"))
        table.add_row("耗时", Text(f"{res.cost_time:.2f}s", style="yellow"))

        # 排名：只有 normal 类型才有意义
        if res.type == "normal":
            if res.rank is None or res.rank < 0:
                rank_cell = Text("资料中未检索到", style="dim")
            elif res.rank <= 4:
                rank_cell = Text(f"第 {res.rank + 1} 位 ✅", style="green")
            else:
                rank_cell = Text(f"第 {res.rank + 1} 位 ❌", style="red")
        else:
            rank_cell = Text("—", style="dim")
        table.add_row("排名", rank_cell)

        if res.is_system_error:
            console.print(Panel(table, border_style="red", title="[bold red]⚠ 系统错误[/bold red]"))
        else:
            console.print(table)

        # 打印详细信息
        console.print("以下是详细链路调用:\n")
        print_one_request_trace(str(res.trace_id))


if __name__ == '__main__':
    # print_one_request_trace("245fbc0b-486d-4a6d-8744-dc5f9a9349d3")
    # print_all_not_passed_request()

    #控制台应用
    while True:
        console.clear()

        console.print("你好！Computer114514，欢迎来到可视化链路系统\n")
        console.print("请选择需要查看的批次/链路:")
        console.print("")
        console.print("[1]最近一批测试")
        console.print("[2]指定一批测试(手动输入run_id)")
        console.print("[3]查看特定请求(手动输3入trace_id)")
        console.print("[4]退出")
        console.print("")
        choice=Prompt.ask("请选择(默认选择1)",choices=['1','2','3','4'],default='1')


        if choice== '1':
            #选择了1，正在检索最近一批测试
            console.print("正在检索最近一批测试的run_id")
            run_id = get_recently_run_id()
            console.print("检索成功")
            while True:
                console.clear()
                console.print("请选择需要查看的链路:")
                console.print("")
                console.print("[0]返回上一级")
                console.print("[1]所有NotPassed的链路")
                console.print("[2]系统错误的链路")
                console.print("[3]非系统错误的NotPassed链路")
                console.print("")
                choice=Prompt.ask("请选择(默认选择1)",choices=['0','1','2','3'],default='1')

                if choice=='0':
                    break
                elif choice=='1':
                    print_all_not_passed_request(run_id)
                elif choice=='2':
                    print_all_not_passed_system_error_request(run_id)
                elif choice=='3':
                    print_all_not_passed_not_system_error_request(run_id)

        elif choice== '2':
            while True:
                run_id=input("请输入run_id,输入0退出:")
                if run_id== '0':
                    break
                with (engine.begin() as conn):
                    pre_sql = select(request_table).where(request_table.c.run_id == run_id)
                    execute_res_all = conn.execute(pre_sql).all()
                    if not execute_res_all:
                        console.print("run_id错误，请重新输入")
                        continue
                    break

            if run_id!= '0':
                while True:
                    console.clear()
                    console.print("请选择需要查看的链路:")
                    console.print("")
                    console.print("[0]返回上一级")
                    console.print("[1]所有NotPassed的链路")
                    console.print("[2]系统错误的链路")
                    console.print("[3]非系统错误的NotPassed链路")
                    console.print("")
                    choice=Prompt.ask("请选择(默认选择1)",choices=['0','1','2','3'],default='1')

                    if choice=='0':
                        break
                    elif choice=='1':
                        print_all_not_passed_request(run_id)
                    elif choice=='2':
                        print_all_not_passed_system_error_request(run_id)
                    elif choice=='3':
                        print_all_not_passed_not_system_error_request(run_id)

        elif choice== '3':
            while True:
                trace_id=input("请输入特定请求的trace_id,输入0退出:")
                if trace_id== '0':
                    break
                with (engine.begin() as conn):
                    pre_sql = select(request_table).where(request_table.c.trace_id == trace_id)
                    execute_res_all = conn.execute(pre_sql).all()
                    if not execute_res_all:
                        print("trace_id错误，请重1新输入")
                        continue
                break
            if trace_id!= '0':
                print_one_request(trace_id)
        elif choice== '4':
            break


