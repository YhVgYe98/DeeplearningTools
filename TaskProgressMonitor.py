from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text
from rich.progress import Progress, BarColumn, TaskProgressColumn, MofNCompleteColumn, TimeRemainingColumn, TimeElapsedColumn, TextColumn
from rich import print

from pathlib import Path
from datetime import datetime
from collections import deque

class TaskProgressMonitor:
    """
    基于 Rich 的终端进度监控器，适用于多阶段任务的进度跟踪。
    支持总体任务进度条、当前子任务进度条、实时信息和静态日志记录。
    同时将日志信息写入文件。
    """

    def __init__(self,
                 live_info_title: str = "Current Status",
                 static_info_title: str = "History Log",
                 filedir: str = './',
                 filename: str = None,
                 max_static_lines: int = 1000):
        # 显示布局
        self.layout = Layout()
        self.layout.split(
            Layout(name="progress_bar", size=3),
            Layout(name="live_info", size=3),
            Layout(name="static_info", ratio=1)
        )
        # 进度条
        self.progress = Progress(
            TextColumn('[progress.description]{task.description}'),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            TextColumn('=>'),
            TimeElapsedColumn(),
            TextColumn('{task.fields[info]}'),
            auto_refresh=True
        )
        self.layout["progress_bar"].update(self.progress)
        
        # 初始化
        self.static_content = deque(maxlen=max_static_lines)
        self.live_info_title = f"[bold]{live_info_title}"
        self.static_info_title = f"[bold]{static_info_title}"
        self.layout["live_info"].update(Panel("Waiting for first update...", title=self.live_info_title))
        self.layout["static_info"].update(Panel('', title=self.static_info_title))

        self.live = Live(self.layout, screen=True, refresh_per_second=10)
        self.overall_task = None
        self.subtask = None
        self._live_started = False
        self._log_file = None

        # 初始化时间记录
        self.start_time = None
        self.end_time = None
        
        # 初始化进度记录
        self._overall_total = 0
        self._overall_completed = 0
        self._subtask_total = 0
        self._subtask_completed = 0
        
        # 创建日志文件路径
        self.filedir = Path(filedir)
        self.filename = filename or datetime.now().strftime("%Y%m%dT%H%M%S") + ".log"
        self.log_file_path = self.filedir / self.filename

    def start(self):
        """手动启动监控器"""
        if self._live_started:
            return
            
        # 确保目录存在
        self.filedir.mkdir(parents=True, exist_ok=True)
        
        # 打开日志文件
        self._log_file = open(self.log_file_path, "a", encoding="utf-8", buffering=-1)
        
        # 记录启动信息
        self._log_file.write(f"================= Log started at {datetime.now().isoformat()} =================\n")
        
        # 启动实时显示
        self.live.start()
        self._live_started = True
        self.start_time = datetime.now()

    def stop(self, success: bool = True):
        """手动停止监控器"""
        if not self._live_started:
            return
            
        self.complete()
        self.live.refresh()
        self.live.stop()
        self.end_time = datetime.now()
        
        # 输出静态内容
        print("\n".join(self.static_content))
        
        # 记录完成信息并关闭文件
        if self._log_file:
            self._log_file.write(f"================= Task completed at {datetime.now().isoformat()} =================\n")
            self._log_file.write(f"================= Time Elapse: {str(self.end_time - self.start_time)} =================\n")
            self._log_file.close()
            self._log_file = None
        
        # 输出完成状态
        if success:
            print("[bold green]✓ Task Completed Successfully[/]")
        else:
            print("[bold red]✗ Task Failed[/]")
        print(f"[bold yellow] Time Elapse: {str(self.end_time - self.start_time)}[/]")
        
        self._live_started = False

    def __enter__(self):
        """支持 with 语句的上下文管理"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """退出上下文时完成任务清理"""
        self.stop(exc_type is None)
        return False

    def init_overall_task(self, title: str, total_phases: int, start_phase: int = 0):
        """
        初始化总体任务进度条（跨所有阶段的总进度）.

        Args:
            title (str): 总体任务描述标题。
            total_phases (int): 总阶段数。
            start_phase (int): 初始已完成的阶段数，默认为 0。
        """
        if not self._live_started:
            raise RuntimeError("Monitor must be started first")

        if self.overall_task:
            self.progress.remove_task(self.overall_task)

        self.overall_task = self.progress.add_task(
            description=f"[cyan]{title}",
            total=total_phases,
            completed=start_phase,
            info=''
        )
        self._overall_total = total_phases
        self._overall_completed = start_phase

    def init_subtask(self, title: str, total_tasks: int):
        """
        初始化当前阶段的子任务进度条.

        Args:
            title (str): 当前阶段描述标题。
            total_tasks (int): 当前阶段的总任务数。
        """
        if not self._live_started:
            raise RuntimeError("Monitor must be started first")
        if total_tasks <= 0:
            raise ValueError("total_tasks must be a positive integer")

        if self.subtask:
            self.progress.remove_task(self.subtask)

        self.subtask = self.progress.add_task(
            description=f"[green]{title}",
            total=total_tasks,
            info=''
        )
        self._subtask_total = total_tasks
        self._subtask_completed = 0

    def update_progress(self, step: int = 1, info: str = ""):
        """
        更新当前子任务的进度及附加信息，并同步更新总体任务进度条。

        Args:
            step (int): 当前步进数量，默认为 1。
            info (str): 需要显示在进度条旁的信息。
        """
        if not self._live_started:
            raise RuntimeError("Monitor must be started first")

        self.progress.update(self.subtask, advance=step, info=info)
        total_advance = step / self._subtask_total
        self.progress.update(self.overall_task, advance=total_advance)
        
        # 更新内部状态
        self._subtask_completed += step
        self._overall_completed += total_advance

    def _log_to_file(self, message: str):
        """将信息记录到日志文件"""
        if not self._log_file:
            return
            
        timestamp = datetime.now().isoformat(timespec='seconds')
        
        # 格式化任务进度信息
        task_progress = f"{self._overall_completed:.2f}/{self._overall_total}"
        subtask_progress = f"{self._subtask_completed}/{self._subtask_total}"
        log_line = f"{timestamp} | {task_progress} | {subtask_progress} | {message}"
        
        self._log_file.write(log_line + "\n")

    def update_live_info(self, info: str):
        """更新实时信息面板内容并记录到日志文件."""
        if not self._live_started:
            raise RuntimeError("Monitor must be started first")
        self.layout["live_info"].update(Panel(info, padding=(0, 2), title=self.live_info_title))
        self._log_to_file(info)

    def update_static_info(self, info: str):
        """将信息追加到静态信息面板并记录到日志文件."""
        if not self._live_started:
            raise RuntimeError("Monitor must be started first")
        
        # 添加到静态内容（使用双端队列自动限制长度）
        self.static_content.append(info)
        
        # 更新显示
        self.layout["static_info"].update(Panel(TailText(self.static_content), title=self.static_info_title))
        
        # 记录日志
        self._log_to_file(info)

    def complete(self):
        """标记任务完成，清理进度条并更新状态提示."""
        if not self._live_started:
            return

        self.layout["live_info"].update(Panel("[bold green]All Tasks Finished![/]"))
        if self.subtask:
            self.progress.remove_task(self.subtask)
            self.subtask = None
        if self.overall_task:
            self.progress.remove_task(self.overall_task)
            self.overall_task = None
        self.live.refresh()


class TailText:
    """显示文本尾部内容的可渲染对象，自动截取至适合面板高度的行数"""
    def __init__(self, text_deque: deque):
        self.text_deque = text_deque
    
    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        # 计算面板内部可用高度
        max_lines = max(1, options.height)
        
        # 转换为列表并截取末尾的N行（N=max_lines）
        display_lines = list(self.text_deque)[-max_lines:]
        
        # 创建新的文本对象
        clipped_text = Text("\n".join(display_lines))
        yield clipped_text


if __name__ == '__main__':
    import time
    task_num = 40
    subtask_num = 12
    
    # 使用 with 语句的示例
    with TaskProgressMonitor() as monitor:
        monitor.init_overall_task('Processing', task_num)
        for i in range(task_num):
            monitor.init_subtask(f'Phase {i}', subtask_num)
            for j in range(subtask_num):
                time.sleep(0.01)
                monitor.update_progress(step=1, info=f"Status: {j}")
                monitor.update_live_info(f"Current task: {j}")
            monitor.update_static_info(f"Phase: {i} completed, total tasks: {task_num}")
    
    # 不使用 with 语句的示例
    monitor = TaskProgressMonitor()
    monitor.start()
    try:
        monitor.init_overall_task('Manual Processing', task_num)
        for i in range(task_num):
            monitor.init_subtask(f'Manual Phase {i}', subtask_num)
            for j in range(subtask_num):
                time.sleep(0.01)
                monitor.update_progress(step=1, info=f"Status: {j}")
                monitor.update_live_info(f"Manual task: {j}")
            monitor.update_static_info(f"Manual Phase: {i} completed")
    finally:
        monitor.stop()
