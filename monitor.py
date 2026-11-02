import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = 'https://open.douyin.com'


def request(path, token, params, body=None):
    url = API + path + '?' + urllib.parse.urlencode(params)
    payload = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'access-token': token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError('接口请求失败，请检查网络或授权状态') from exc
    for section in ('data', 'extra'):
        info = result.get(section) or {}
        if str(info.get('error_code', 0)) != '0':
            raise RuntimeError(f"抖音接口错误 {info.get('error_code')}: {info.get('description', '')}")
    return result.get('data') or {}


def fetch_fans(token, open_id):
    data = request('/data/external/user/fans/', token, {'open_id': open_id, 'date_type': 7})
    rows = data.get('result_list') or []
    if not rows:
        raise RuntimeError('暂无粉丝数据，首次授权后可能需要等待平台更新')
    row = max(rows, key=lambda x: x['date'])
    return int(row['total_fans']), row['date']


def fetch_videos(token, open_id, ids):
    videos = []
    for start in range(0, len(ids), 10):
        batch = ids[start:start + 10]
        data = request('/video/data/', token, {'open_id': open_id}, {'item_ids': batch})
        for row in data.get('list') or []:
            stats = row.get('statistics') or {}
            if row.get('item_id') in batch and row.get('create_time') != 0 and stats.get('play_count') is not None:
                videos.append((row['item_id'], row.get('title') or '未命名视频', int(stats['play_count'])))
    return videos


def database(path):
    db = sqlite3.connect(path)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS fans (account TEXT, collected_at TEXT, data_date TEXT, count INTEGER);
        CREATE TABLE IF NOT EXISTS videos (account TEXT, collected_at TEXT, item_id TEXT, title TEXT, count INTEGER);
        CREATE INDEX IF NOT EXISTS fans_account_time ON fans(account, collected_at);
        CREATE INDEX IF NOT EXISTS videos_account_item_time ON videos(account, item_id, collected_at);
    ''')
    return db


def difference(now, previous):
    if previous is None:
        return '首次记录'
    delta = now - previous
    percent = '，基数为 0' if previous == 0 else f'，{delta / previous * 100:+.2f}%'
    return f'{delta:+,}{percent}'


def save_fans(db, account, stamp, count, date):
    row = db.execute('SELECT count FROM fans WHERE account=? ORDER BY rowid DESC LIMIT 1', (account,)).fetchone()
    db.execute('INSERT INTO fans VALUES (?,?,?,?)', (account, stamp, date, count))
    db.commit()
    print(f'粉丝 {count:,}  | 较上次 {difference(count, row[0] if row else None)}  | 平台数据日期 {date}')


def save_videos(db, account, stamp, videos):
    for item_id, title, count in videos:
        row = db.execute('SELECT count FROM videos WHERE account=? AND item_id=? ORDER BY rowid DESC LIMIT 1', (account, item_id)).fetchone()
        db.execute('INSERT INTO videos VALUES (?,?,?,?,?)', (account, stamp, item_id, title, count))
        print(f'播放 {count:,}  | 较上次 {difference(count, row[0] if row else None)}  | {title} [{item_id}]')
    db.commit()


def cycle(db, config, token, demo=False):
    stamp = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    account = 'demo' if demo else config['open_id']
    print(f'\n[{stamp}] 本次采集', flush=True)
    errors = 0
    try:
        if demo:
            previous = db.execute('SELECT count FROM fans WHERE account=? ORDER BY rowid DESC LIMIT 1', (account,)).fetchone()
            fans, date = (previous[0] + 3 if previous else 1280), dt.date.today().isoformat()
        else:
            fans, date = fetch_fans(token, account)
        save_fans(db, account, stamp, fans, date)
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f'粉丝采集失败：{exc}', file=sys.stderr, flush=True)
        errors += 1
    try:
        if demo:
            previous = db.execute('SELECT count FROM videos WHERE account=? AND item_id=? ORDER BY rowid DESC LIMIT 1', (account, 'demo-video')).fetchone()
            videos = [('demo-video', '示例作品（模拟数据）', previous[0] + 168 if previous else 23500)]
            expected = ['demo-video']
        else:
            expected = config['item_ids']
            videos = fetch_videos(token, account, expected)
        save_videos(db, account, stamp, videos)
        missing = set(expected) - {v[0] for v in videos}
        if missing:
            print('未返回播放数据（可能未公开或 ID 无效）：' + ', '.join(sorted(missing)), file=sys.stderr, flush=True)
            errors += 1
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f'视频采集失败：{exc}', file=sys.stderr, flush=True)
        errors += 1
    return errors == 0


def main():
    parser = argparse.ArgumentParser(description='抖音账号小助手：定时采集粉丝与指定视频播放量')
    parser.add_argument('--config', default=str(ROOT / 'config.json'), help='配置文件路径')
    parser.add_argument('--db', default=str(ROOT / 'monitor.db'), help='SQLite 数据库路径')
    parser.add_argument('--once', action='store_true', help='采集一次后退出')
    parser.add_argument('--demo', action='store_true', help='使用模拟数据，不请求抖音')
    parser.add_argument('--history', action='store_true', help='查看最近的采集记录')
    args = parser.parse_args()
    if args.history:
        if not Path(args.db).exists():
            parser.error('数据库不存在，请先采集数据')
        with database(args.db) as db:
            print('最近粉丝记录：')
            for stamp, date, count in db.execute('SELECT collected_at, data_date, count FROM fans ORDER BY rowid DESC LIMIT 20'):
                print(f'{stamp} | 粉丝 {count:,} | 平台日期 {date}')
            print('\n最近视频记录：')
            for stamp, title, item_id, count in db.execute('SELECT collected_at, title, item_id, count FROM videos ORDER BY rowid DESC LIMIT 20'):
                print(f'{stamp} | 播放 {count:,} | {title} [{item_id}]')
        return 0
    config = {}
    if not args.demo:
        try:
            config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
            if not isinstance(config.get('open_id'), str) or not config['open_id'].strip():
                raise ValueError('请填写 open_id')
            ids = config.get('item_ids')
            if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x.strip() for x in ids) or len(set(ids)) != len(ids):
                raise ValueError('item_ids 需要填写不重复的视频 ID 列表')
            token = os.environ.get('DOUYIN_ACCESS_TOKEN', '').strip()
            if not token:
                raise ValueError('请先设置环境变量 DOUYIN_ACCESS_TOKEN')
        except (OSError, ValueError, TypeError) as exc:
            parser.error(str(exc))
    else:
        token = ''
    try:
        interval = int(config.get('interval_seconds', 300))
        if interval < 1:
            raise ValueError()
    except (ValueError, TypeError):
        parser.error('interval_seconds 必须是大于 0 的整数')
    with database(args.db) as db:
        while True:
            started = time.monotonic()
            ok = cycle(db, config, token, args.demo)
            if args.once:
                return 0 if ok else 1
            print(f'下次采集将在约 {interval} 秒后开始；按 Ctrl+C 停止。', flush=True)
            time.sleep(max(0, interval - (time.monotonic() - started)))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n监控已停止。')
