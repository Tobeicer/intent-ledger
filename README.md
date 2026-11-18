# Intent Ledger

让 Codex 记住一个项目当前定下来的事。用自己的话提要求；换个聊天继续做，或在另一个项目定下相反的规则。

原话在用户提交时由 Hook 保存。是否构成长期决定由正在对话的模型判断，没有第二次模型调用。每条决定指回用户原文；同一项目、同一主题只有最新版本生效。比如「以后订单导出用 CSV」可以被「以后改用 JSON」替换。「这次先给我 CSV」和「要不要试试 XML？」只应留下原话。模型可能漏记或归错主题，可以随时核对。

## 安装与启用

需要支持本地插件、MCP 和 `UserPromptSubmit` 的 Codex，以及在 PATH 上可通过 `python` 启动的 Python 3.9+。无需 pip 安装依赖。

```sh
git clone https://github.com/Tobeicer/intent-ledger.git
cd intent-ledger
python plugin/ledger.py setup
```

安装器用 Codex 自带命令安装这个本地插件，并在用户的 `hooks.json` 中合并一个记录器。它指向实际安装的版本；不会替换其他 Hook。打开新的 Codex CLI 会话，输入 `/hooks`，检查并信任 **Intent Ledger: local project memory**。桌面应用如未刷新，请重新打开。若 Codex 提示是否允许插件工具保存决定，请按需授权；不授权时仍可能有原话，但不会新增决定。

只给需要记忆的项目开启记录。将下面的路径替换成自己的**项目根目录**：

```sh
python plugin/ledger.py enable "/path/to/project"
python plugin/ledger.py status "/path/to/project"
```

在已开启的目录新开一个聊天，说「以后发给客户的文件统一用 PDF」，再说「以后改成 DOCX」。另开一个同目录的聊天问「发给客户用什么格式？」。可用以下命令核对当前决定、用户原话或暂停记录：

```sh
python plugin/ledger.py show "/path/to/project"
python plugin/ledger.py messages "/path/to/project"
python plugin/ledger.py disable "/path/to/project"
```

## 范围和数据

- 默认不记录任何项目。范围取注册目录的规范绝对路径；同名目录、不同克隆和 worktree 分开。子目录沿用最近的注册目录；独立的嵌套 Git 仓库和显式停用的目录不会继承。移动或重命名项目会改变它的身份。
- 保存的是 Codex 通过提交事件交付的**用户文本**。不回填安装前的聊天，不读取附件、工具输出或助手全文。数据库不随代码提交。记录器自身不联网；相关有效决定会随当前聊天提供给所用的模型。
- 数据库是本机当前用户目录下的明文 SQLite：Windows 为 `%LOCALAPPDATA%/intent-ledger/memory.sqlite3`，其他平台默认 `~/.local/share/intent-ledger/memory.sqlite3`（支持 `XDG_DATA_HOME`）。每次仅带回最多八条当前决定，需要时可搜索本项目的其他主题。原文不随历史反复发送。
- 保存需要本轮来源 ID、原话摘录和当前版本号。并发修改有冲突会拒写；旧消息不能覆盖同主题更新的决定。项目隔离用于防止正常协作中串记忆，不是操作系统账户间的权限边界。
- `disable` 保留历史数据。`python plugin/ledger.py unhook` 只移除此记录器；`codex plugin remove intent-ledger@intent-ledger-local` 移除插件。需要清空所有项目历史时，关闭使用插件的会话后删除上述数据库。

## 验证

```sh
python -B -m unittest discover -s tests -v
```

测试使用临时数据库。覆盖同名的两个项目、跨进程回读、版本替换、旧消息回写、原话保真、嵌套项目和停用状态。

0.1.0 也在 Windows 的真实 Codex 会话中验证过：项目 A 把清单名从「青檐单」改为「雾桥单」，项目 B 定为「海盐单」。分别新开聊天，只问「这个项目的交付清单叫什么？」，得到「雾桥单」和「海盐单」。数据库中 A 有两版决定，B 只有一版。

[MIT License](LICENSE) · [Codex Hooks](https://learn.chatgpt.com/docs/hooks) · [本地插件](https://developers.openai.com/plugins/build/plugins)
