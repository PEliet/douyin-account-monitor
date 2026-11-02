"""本地桌面界面；所有网络请求在后台线程中执行。"""
from contextlib import closing
import datetime as dt
import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import monitor

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'monitor.db'
BG = '#f4f5f3'
INK = '#202a29'
MUTED = '#65716e'
GREEN = '#167966'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('账号小助手')
        self.geometry('1100x760')
        self.minsize(800, 600)
        self.configure(bg=BG)
        self.events = queue.Queue()
        self.running = False
        self.busy = False
        self.job = None
        self.current = None
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.style_setup()
        self.make_ui()
        self.load_config()
        self.after(150, self.poll)

    def style_setup(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10), background=BG, foreground=INK)
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 21, 'bold'))
        style.configure('Heading.TLabel', font=('Microsoft YaHei UI', 12, 'bold'))
        style.configure('Metric.TLabel', font=('Microsoft YaHei UI', 24, 'bold'), foreground=INK)
        style.configure('Muted.TLabel', foreground=MUTED)
        style.configure('Primary.TButton', background=GREEN, foreground='white', padding=(14, 8))
        style.map('Primary.TButton', background=[('active', '#116b5b'), ('disabled', '#a2b9b2')], foreground=[('disabled', '#f4f5f3')])
        style.configure('TButton', padding=(10, 7))
        style.configure('Treeview', rowheight=32, background='white', fieldbackground='white', borderwidth=0)
        style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 9, 'bold'))

    def make_ui(self):
        outer = ttk.Frame(self, padding=24)
        outer.pack(fill='both', expand=True)
        header = ttk.Frame(outer)
        header.pack(fill='x')
        ttk.Label(header, text='账号小助手', style='Title.TLabel').pack(side='left')
        self.status = tk.StringVar(value='尚未开始监控')
        ttk.Label(header, textvariable=self.status, style='Muted.TLabel').pack(side='right')
        ttk.Label(outer, text='粉丝与作品播放表现，随时掌握。', style='Muted.TLabel').pack(anchor='w', pady=(3, 15))

        form = ttk.LabelFrame(outer, text='采集设置', padding=12)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        self.mode = tk.BooleanVar(value=True)
        self.open_id = tk.StringVar()
        self.token = tk.StringVar(value=os.environ.get('DOUYIN_ACCESS_TOKEN', ''))
        self.ids = tk.StringVar()
        self.interval = tk.StringVar(value='300')
        self.mode_check = ttk.Checkbutton(form, text='模拟模式', variable=self.mode, command=self.mode_changed)
        self.mode_check.grid(row=0, column=0, sticky='w', padx=(0, 10))
        ttk.Label(form, text='间隔（秒）').grid(row=0, column=2, sticky='e', padx=8)
        self.interval_entry = ttk.Entry(form, textvariable=self.interval, width=10)
        self.interval_entry.grid(row=0, column=3, sticky='w')
        ttk.Label(form, text='Open ID').grid(row=1, column=0, sticky='w', pady=5)
        self.open_entry = ttk.Entry(form, textvariable=self.open_id)
        self.open_entry.grid(row=1, column=1, sticky='ew', padx=(0, 12))
        ttk.Label(form, text='Access Token').grid(row=1, column=2, sticky='e', padx=8)
        self.token_entry = ttk.Entry(form, textvariable=self.token, show='•')
        self.token_entry.grid(row=1, column=3, sticky='ew')
        ttk.Label(form, text='作品 ID').grid(row=2, column=0, sticky='w')
        self.ids_entry = ttk.Entry(form, textvariable=self.ids)
        self.ids_entry.grid(row=2, column=1, columnspan=3, sticky='ew')
        ttk.Label(form, text='多个 item_id 用英文逗号分隔。令牌只保存在本次运行的内存中。', style='Muted.TLabel').grid(row=3, column=1, columnspan=3, sticky='w', pady=(4, 0))
        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=12)
        self.start_btn = ttk.Button(actions, text='开始监控', style='Primary.TButton', command=self.start)
        self.start_btn.pack(side='left')
        self.stop_btn = ttk.Button(actions, text='停止监控', command=self.stop, state='disabled')
        self.stop_btn.pack(side='left', padx=8)
        self.once_btn = ttk.Button(actions, text='采集一次', command=self.once)
        self.once_btn.pack(side='left')
        self.view_btn = ttk.Button(actions, text='查看已有记录', command=self.show_existing)
        self.view_btn.pack(side='left', padx=8)
        self.summary = tk.StringVar(value='选择模拟模式开始，或填写授权信息查看真实数据。')
        ttk.Label(outer, textvariable=self.summary, style='Muted.TLabel', wraplength=1000).pack(anchor='w', pady=(0, 10))

        metrics = ttk.Frame(outer)
        metrics.pack(fill='x', pady=(0, 12))
        self.fans_value = tk.StringVar(value='—')
        self.fans_delta = tk.StringVar(value='暂无采集记录')
        self.video_count = tk.StringVar(value='—')
        self.updated = tk.StringVar(value='等待采集')
        for parent, title, value, detail in [(metrics, '粉丝总数', self.fans_value, self.fans_delta), (metrics, '有记录的作品', self.video_count, self.updated)]:
            box = ttk.Frame(parent, padding=(4, 0, 30, 0))
            box.pack(side='left', fill='x', expand=True)
            ttk.Label(box, text=title, style='Muted.TLabel').pack(anchor='w')
            ttk.Label(box, textvariable=value, style='Metric.TLabel').pack(anchor='w')
            ttk.Label(box, textvariable=detail, style='Muted.TLabel').pack(anchor='w')

        content = ttk.Panedwindow(outer, orient='horizontal')
        content.pack(fill='both', expand=True)
        left = ttk.Frame(content, padding=(0, 0, 14, 0))
        right = ttk.Frame(content)
        content.add(left, weight=3)
        content.add(right, weight=2)
        title_row = ttk.Frame(left)
        title_row.pack(fill='x')
        ttk.Label(title_row, text='历史趋势', style='Heading.TLabel').pack(side='left')
        self.series = tk.StringVar()
        self.series_box = ttk.Combobox(title_row, textvariable=self.series, state='readonly', width=28)
        self.series_box.pack(side='right')
        self.series_box.bind('<<ComboboxSelected>>', lambda e: self.draw_chart())
        self.chart = tk.Canvas(left, background='white', highlightthickness=0, height=250)
        self.chart.pack(fill='both', expand=True, pady=(8, 0))
        self.chart.bind('<Configure>', lambda e: self.draw_chart())
        ttk.Label(left, text='按采集时间展示最近 50 条记录。粉丝数据通常按日更新。', style='Muted.TLabel', wraplength=500).pack(anchor='w', pady=(8, 0))
        ttk.Label(right, text='作品播放', style='Heading.TLabel').pack(anchor='w')
        columns = ('title', 'count', 'delta')
        self.tree = ttk.Treeview(right, columns=columns, show='headings', selectmode='browse', height=7)
        for col, title, width in [('title', '作品', 180), ('count', '播放量', 85), ('delta', '较上次', 100)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=65, stretch=(col == 'title'), anchor='w')
        self.tree.pack(fill='both', expand=True, pady=(8, 0))
        self.tree.bind('<<TreeviewSelect>>', self.select_video)
        ttk.Label(right, text='选择作品可查看其播放趋势。', style='Muted.TLabel').pack(anchor='w', pady=(8, 0))
        self.mode_changed()

    def load_config(self):
        try:
            data = json.loads((ROOT / 'config.json').read_text(encoding='utf-8-sig'))
            self.open_id.set(data.get('open_id', ''))
            self.ids.set(', '.join(data.get('item_ids', [])))
            self.interval.set(str(data.get('interval_seconds', 300)))
        except (OSError, ValueError, TypeError):
            pass

    def mode_changed(self):
        state = 'disabled' if self.mode.get() else 'normal'
        for entry in (self.open_entry, self.token_entry, self.ids_entry):
            entry.configure(state=state)

    def settings(self):
        try:
            interval = int(self.interval.get())
            if interval < 1:
                raise ValueError
        except ValueError:
            raise ValueError('采集间隔必须为大于 0 的整数。')
        demo = self.mode.get()
        account = 'demo' if demo else self.open_id.get().strip()
        ids = [x.strip() for x in self.ids.get().split(',') if x.strip()]
        token = self.token.get().strip()
        if not demo and (not account or not ids or not token):
            raise ValueError('请填写 Open ID、Access Token 和至少一个作品 ID。')
        if len(set(ids)) != len(ids):
            raise ValueError('作品 ID 不能重复。')
        return {'open_id': account, 'item_ids': ids, 'interval_seconds': interval}, token, demo

    def start(self):
        try:
            self.current = self.settings()
        except ValueError as exc:
            messagebox.showerror('检查采集设置', str(exc), parent=self)
            return
        self.running = True
        self.start_btn.configure(state='disabled')
        self.once_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal')
        self.lock_form(True)
        self.run_cycle()

    def once(self):
        try:
            self.current = self.settings()
        except ValueError as exc:
            messagebox.showerror('检查采集设置', str(exc), parent=self)
            return
        self.lock_form(True)
        self.once_btn.configure(state='disabled')
        self.start_btn.configure(state='disabled')
        self.run_cycle()

    def lock_form(self, locked):
        self.view_btn.configure(state='disabled' if locked else 'normal')
        self.mode_check.configure(state='disabled' if locked else 'normal')
        self.interval_entry.configure(state='disabled' if locked else 'normal')
        if locked:
            for entry in (self.open_entry, self.token_entry, self.ids_entry):
                entry.configure(state='disabled')
        else:
            self.mode_changed()

    def stop(self):
        self.running = False
        if self.job:
            self.after_cancel(self.job)
            self.job = None
        self.status.set('正在完成本次采集…' if self.busy else '监控已停止')
        self.stop_btn.configure(state='disabled')
        if not self.busy:
            self.unlock()

    def unlock(self):
        self.start_btn.configure(state='normal')
        self.once_btn.configure(state='normal')
        self.stop_btn.configure(state='disabled')
        self.lock_form(False)

    def run_cycle(self):
        if self.busy:
            return
        self.busy = True
        self.status.set('正在采集…')
        threading.Thread(target=self.worker, args=self.current, daemon=True).start()

    def worker(self, config, token, demo):
        errors = []
        account = config['open_id']
        stamp = dt.datetime.now().astimezone().isoformat(timespec='seconds')
        try:
            with closing(monitor.database(DB)) as db:
                try:
                    if demo:
                        old = db.execute('SELECT count FROM fans WHERE account=? ORDER BY rowid DESC LIMIT 1', (account,)).fetchone()
                        fans, date = (old[0] + 3 if old else 1280), dt.date.today().isoformat()
                    else:
                        fans, date = monitor.fetch_fans(token, account)
                    monitor.save_fans(db, account, stamp, fans, date)
                except (RuntimeError, ValueError, KeyError, TypeError) as exc:
                    errors.append('粉丝：' + str(exc))
                try:
                    if demo:
                        old = db.execute('SELECT count FROM videos WHERE account=? AND item_id=? ORDER BY rowid DESC LIMIT 1', (account, 'demo-video')).fetchone()
                        videos = [('demo-video', '示例作品（模拟数据）', old[0] + 168 if old else 23500)]
                        expected = ['demo-video']
                    else:
                        expected = config['item_ids']
                        videos = monitor.fetch_videos(token, account, expected)
                    monitor.save_videos(db, account, stamp, videos)
                    missing = set(expected) - {v[0] for v in videos}
                    if missing:
                        errors.append('未返回作品：' + ', '.join(sorted(missing)))
                except (RuntimeError, ValueError, KeyError, TypeError) as exc:
                    errors.append('作品：' + str(exc))
        except Exception as exc:
            errors.append('采集失败：' + str(exc))
        self.events.put((account, stamp, errors))

    def poll(self):
        try:
            account, stamp, errors = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.show_account(account)
            self.summary.set('；'.join(errors) if errors else ('模拟数据 · ' if account == 'demo' else '') + '采集成功。粉丝数为平台提供的按日数据。')
            if self.running:
                self.status.set('监控中 · 上次采集 ' + stamp[11:19])
                self.job = self.after(self.current[0]['interval_seconds'] * 1000, self.run_cycle)
            else:
                self.status.set('已停止 · 上次采集 ' + stamp[11:19])
                self.unlock()
        self.after(150, self.poll)

    def show_existing(self):
        account = 'demo' if self.mode.get() else self.open_id.get().strip()
        if not account:
            messagebox.showerror('查看记录', '请填写要查看的账号 Open ID。', parent=self)
            return
        self.show_account(account)
        self.summary.set(('模拟账号' if account == 'demo' else '当前账号') + '的历史记录；此操作不会启动监控。')

    def show_account(self, account):
        self.account = account
        with closing(monitor.database(DB)) as db:
            fans = db.execute('SELECT collected_at, data_date, count FROM fans WHERE account=? ORDER BY rowid DESC LIMIT 2', (account,)).fetchall()
            rows = db.execute('SELECT item_id, title, count, collected_at FROM videos WHERE account=? ORDER BY rowid DESC', (account,)).fetchall()
        self.fans_value.set(f'{fans[0][2]:,}' if fans else '—')
        self.fans_delta.set(('较上次 ' + monitor.difference(fans[0][2], fans[1][2] if len(fans) > 1 else None) + ' · 数据日期 ' + fans[0][1]) if fans else '暂无采集记录')
        latest = {}
        for item_id, title, count, stamp in rows:
            latest.setdefault(item_id, []).append((title, count, stamp))
        self.video_count.set(str(len(latest)))
        self.updated.set('作品数据按各自最近一次成功采集显示' if latest else '暂无作品记录')
        self.tree.delete(*self.tree.get_children())
        self.series_map = {'粉丝总数': None}
        for idx, (item_id, entries) in enumerate(latest.items()):
            title, count, stamp = entries[0]
            previous = entries[1][1] if len(entries) > 1 else None
            self.tree.insert('', 'end', iid=str(idx), values=(title, f'{count:,}', monitor.difference(count, previous)))
            self.series_map[f'{title} [{item_id}]'] = item_id
        old = self.series.get()
        self.series_box['values'] = list(self.series_map)
        self.series.set(old if old in self.series_map else '粉丝总数')
        self.draw_chart()

    def select_video(self, event):
        selection = self.tree.selection()
        if selection and hasattr(self, 'series_map'):
            options = list(self.series_map)
            self.series.set(options[int(selection[0]) + 1])
            self.draw_chart()

    def draw_chart(self):
        c = self.chart
        c.delete('all')
        w, h = c.winfo_width(), c.winfo_height()
        if not hasattr(self, 'account') or not hasattr(self, 'series_map'):
            c.create_text(w / 2, h / 2, text='开始采集后，趋势将显示在这里', fill=MUTED)
            return
        item = self.series_map.get(self.series.get())
        with closing(monitor.database(DB)) as db:
            if item is None:
                rows = db.execute('SELECT collected_at, count FROM fans WHERE account=? ORDER BY rowid DESC LIMIT 50', (self.account,)).fetchall()
            else:
                rows = db.execute('SELECT collected_at, count FROM videos WHERE account=? AND item_id=? ORDER BY rowid DESC LIMIT 50', (self.account, item)).fetchall()
        rows.reverse()
        if not rows:
            c.create_text(w / 2, h / 2, text='暂无记录，采集后即可查看趋势', fill=MUTED)
            return
        if w < 100 or h < 100:
            return
        values = [row[1] for row in rows]
        low, high = min(values), max(values)
        spread = max(high - low, 1)
        x0, x1, y0, y1 = 65, w - 20, 28, h - 40
        for i in range(3):
            y = y0 + (y1 - y0) * i / 2
            label = high - spread * i / 2 if high != low else high
            c.create_line(x0, y, x1, y, fill='#e7ece9')
            c.create_text(x0 - 8, y, text=f'{label:,.0f}', anchor='e', fill=MUTED, font=('Microsoft YaHei UI', 9))
        points = []
        for i, value in enumerate(values):
            x = x0 + (x1 - x0) * i / max(len(values) - 1, 1)
            y = (y0 + y1) / 2 if high == low else y1 - (value - low) / spread * (y1 - y0)
            points.extend((x, y))
        if len(rows) > 1:
            c.create_line(*points, fill=GREEN, width=2)
        for x, y in zip(points[::2], points[1::2]):
            c.create_oval(x-3, y-3, x+3, y+3, fill=GREEN, outline=GREEN)
        c.create_text(x0, h-14, text=rows[0][0][:16].replace('T', ' '), anchor='w', fill=MUTED, font=('Microsoft YaHei UI', 9))
        if len(rows) > 1:
            c.create_text(x1, h-14, text=rows[-1][0][:16].replace('T', ' '), anchor='e', fill=MUTED, font=('Microsoft YaHei UI', 9))

    def close(self):
        self.running = False
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
