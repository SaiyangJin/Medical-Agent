from rich.table import Table
from rich.console import Console


if __name__ == '__main__':
    console=Console()
    console.print("[bold]加粗[/bold]")
    console.print("[red]红色[/red]")
    console.print("[bold red]又粗又红[/bold red]")
    console.print("[dim]变灰 —— 适合次要信息[/dim]")
    console.print("[cyan]青色[/cyan]  [yellow]黄色[/yellow]  [green]绿色[/green]")
    console.rule()                         # ────────────────────
    console.rule("第 3 批")                # ──────── 第 3 批 ────────
    console.rule("[red]❌ 失败了[/red]")

    table = Table(title="评测指标", show_lines=True)
    table.add_column("指标",     style="cyan", no_wrap=True)
    table.add_column("实际",     justify="right")
    table.add_column("门槛",     justify="right")
    table.add_column("结果",     justify="center")

    table.add_row("通过率",     "100%",  "90%",  "✅")
    table.add_row("危险识别率",  "100%",  "100%", "✅")
    table.add_row("Recall@5",  "40%",   "80%",  "❌")
    table.add_row("MRR",       "0.117", "0.5",  "❌")

    console.print(table)