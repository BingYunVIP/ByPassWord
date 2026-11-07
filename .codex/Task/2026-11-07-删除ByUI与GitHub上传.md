# 删除ByUI、本机部署与GitHub上传

日期：2026-11-07（Asia/Singapore）。状态：删除完成、本机部署健康、GitHub源码首发已核验成功。

授权见[记录](../Permissions/2026-11-07-删除ByUI与GitHub上传授权.md)。目标GitHub BingYunVIP/ByPassWord，远程main；当前WSL服务仅127.0.0.1:899。

- [x] 核实ByUI仅有未跟踪依赖残留，删除并确认不存在；Third保留。
- [x] SSH只读核验目标仓库可访问且没有分支；原项目未配置remote。
- [x] 当前运行服务active/healthy；后端45运行文件、前端77构建输入与独立QA发布完全一致，无业务版本变化，因此不做无意义重启或真实数据迁移。
- [x] 检查26个本地提交/362个独立历史blob及当前候选；命中旧演示密码/API/TOTP/私钥样式资料，来源未知，未试用凭据。
- [x] Developer清空Third参考默认条目；独立QA复核2内联JS、6张截图、归档、ignore和当前发布文件/运行健康通过。
- [x] 已保存当前源码/测试/文档到本地提交8c3f835，旧分支重命名codex/local-history-20261107；无父main首发快照0c47af4，旧本地提交完整保留。
- [x] origin配置指定SSH目标，普通push main成功，已跟踪origin/main，无force/merge。
- [x] SSH ls-remote核实远端main等于首发提交0c47af4；本机健康200、服务active/enabled；收尾文档保存后再次核验最终HEAD及工作区。

不上传真实数据库、环境文件、备份密钥或运行日志；已审查的脱敏测试报告随代码交付。首次远端只传清理后当前树，避免旧演示凭据的历史误上传。

源码首发成功：`0c47af48c546cbee04603bd89c52f1a539e8e148`，211个文件；旧历史仅本地保留分支。收尾记录见[发布验证](../Test/2026-11-07-GitHub发布验证.md)，此后只提交该收尾文档与索引/进度，不改业务代码。
