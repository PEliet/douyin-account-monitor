# 抖音账号小助手

一个本地 Python 脚本，默认每 5 分钟采集一次授权账号的粉丝数和指定视频的播放量，显示相对上次成功采集的增减数量与百分比，并将数据保存到 SQLite，供日后查看。不需要第三方 Python 库。

## 运行环境

Python 3.9 或更新版本，设备需联网。监控只在脚本运行时生效；关闭终端或关机后不会继续采集。

## 先体验

在项目目录打开 PowerShell：

```powershell
python monitor.py --demo --once
python monitor.py --demo --once
python monitor.py --history
```

模拟模式生成示例数据，不连接抖音。连续运行 `python monitor.py --demo` 可以体验定时采集。模拟账号与真实账号分开保存。

## 接入自己的抖音账号

1. 在[抖音开放平台](https://open.douyin.com/)创建应用，按平台要求申请 `data.external.user` 和 `video.data` 能力，并完成账号授权。获取该授权用户的 `open_id` 和用户 `access_token`。本项目不提供 OAuth 授权流程或令牌自动续期；令牌过期后需重新取得并重启脚本。
2. 通过开放平台支持的视频分享结果查询或发布接口取得对应账号作品的 `item_id`。请使用接口返回的 `item_id`，不是随意从链接复制的视频编号。只会监控配置中列出的作品；新增作品需自行加入配置并重启。
3. 将 `config.example.json` 复制为 `config.json`，填写 `open_id` 和 `item_ids`。默认间隔 300 秒，可修改 `interval_seconds`；配置多个作品时每批最多查询 10 个。
4. 在当前 PowerShell 会话设置令牌并启动：

```powershell
$env:DOUYIN_ACCESS_TOKEN = '替换为授权用户的 access_token'
python monitor.py
```

按 `Ctrl+C` 停止。`python monitor.py --once` 只采集一次；`python monitor.py --history` 查看最近 20 条粉丝记录和最近 20 条视频记录。可用 `--config 路径` 和 `--db 路径` 指定配置及数据库文件。默认数据库是项目目录的 `monitor.db`，请妥善保存；配置文件及数据库已列入 `.gitignore`。

## 数据口径

- [粉丝接口](https://open.douyin.com/platform/resource/docs/openapi/data-open-service/user-data/get-user-fans-count)提供按日数据，官方说明昨日数据通常在次日 12 点左右更新。因此五分钟采集不等于五分钟实时粉丝变化；输出中的平台数据日期可用于判断新鲜度。
- [视频数据接口](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/video-data/)提供指定公开作品的实时数据；不可见、无效或未返回的作品会提示，不会当作零。平台权限、审核、限频和接口变动可能影响获取。
- 增减值按同一账号、同一指标的**上一次成功采集**计算；首次采集无涨幅，旧值为零时不计算百分比。粉丝与视频分开保存，一方失败不影响另一方。作品逐个比较，添加或移除作品不会制造虚假的总播放增量。
- 定时循环遇到接口错误会输出原因并在下一轮继续；单次运行有采集失败时返回非零退出码。若需长期运行，请自行使用系统任务计划程序或服务管理工具，确保进程持续运行并根据平台限制调整间隔。
