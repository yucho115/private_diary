# Diary MCP Server

Claude Desktop から既存の Django Diary App を操作するための MCP サーバーです。

```text
Claude Desktop
  -> Diary MCP Server
  -> Django Diary App
  -> PostgreSQL
```

## セットアップ

このサーバーは Django ORM を使うため、既存アプリと同じ環境変数が必要です。

- `DB_USER`
- `DB_PASSWORD`
- 必要なら `DJANGO_SETTINGS_MODULE`

MCP SDK が未インストールの場合は、仮想環境で次を実行してください。

```powershell
pip install "mcp[cli]"
```

## 起動確認

プロジェクト直下で実行します。

```powershell
cd C:\Users\8vill\venv-private-diary\private_diary
python -m mcp_server.server
```

通常は Claude Desktop が stdio で起動するため、手動実行時は待機状態になります。

## Claude Desktop 設定例

`claude_desktop_config.json` に追加します。`python` は実際に使う仮想環境の Python への絶対パスに置き換えてください。

```json
{
  "mcpServers": {
    "private-diary": {
      "command": "C:\\Users\\8vill\\venv-private-diary\\Scripts\\python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "C:\\Users\\8vill\\venv-private-diary\\private_diary",
      "env": {
        "DJANGO_SETTINGS_MODULE": "private_diary.settings_dev",
        "DB_USER": "your_postgres_user",
        "DB_PASSWORD": "your_postgres_password"
      }
    }
  }
}
```

## 使える tools

- `list_users`: ユーザー一覧
- `list_diaries`: 指定ユーザーの日記一覧
- `search_diaries`: タイトル・本文検索
- `get_diary`: 日記詳細
- `create_diary`: 日記作成
- `update_diary`: 日記更新
- `delete_diary`: 日記削除

日記操作では `user_id`、`email`、`username` のいずれかでユーザーを指定できます。
