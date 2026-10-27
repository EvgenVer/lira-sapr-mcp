# Эксплуатация

Как запустить сервер, подключить его к агенту, настроить, проверить и где искать
причину, если что-то не работает.

## Что нужно

- Windows с установленной и лицензированной ЛИРА-САПР 2024 R2 или новее. Сервер
  запускает ЛИРУ сам, если она не запущена; ключ лицензии должен быть доступен.
- [uv](https://docs.astral.sh/uv/) — он сам поставит нужный Python и библиотеки в
  папку `.venv` проекта.

## Установка

В папке проекта:

```bash
uv sync
```

Проверка, что сервер запускается:

```bash
uv run lira-sapr-mcp --version
```

Установка через `uvx` прямо с GitHub появится на этапе 4.

## Подключение к агенту

Сервер — локальный MCP-сервер по stdio: MCP-клиент сам запускает его как процесс и
общается через его стандартный ввод-вывод. Везде указывается одна и та же команда:
`uv --directory <папка проекта> run lira-sapr-mcp`.

Claude Code:

```bash
claude mcp add lira-sapr -- uv --directory "D:\my program\Lira-Sapr-MCP" run lira-sapr-mcp
```

Codex — в файле `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.lira-sapr]
command = "uv"
args = ["--directory", "D:\\my program\\Lira-Sapr-MCP", "run", "lira-sapr-mcp"]
```

Клиенты с JSON-настройкой (Claude Desktop, Cursor и другие):

```json
{
  "mcpServers": {
    "lira-sapr": {
      "command": "uv",
      "args": ["--directory", "D:\\my program\\Lira-Sapr-MCP", "run", "lira-sapr-mcp"]
    }
  }
}
```

Первый вызов агента — `lira_status`: он покажет найденные версии ЛИРЫ и выбранную.

## Настройки

Необязательный файл `%APPDATA%\lira-sapr-mcp\config.toml` (другой путь — переменная
окружения `LIRA_MCP_CONFIG`). Неизвестный ключ — ошибка при запуске, чтобы опечатка не
прошла незамеченной.

```python title="src/lira_sapr_mcp/config.py"
--8<-- "src/lira_sapr_mcp/config.py:settings"
```

Пример:

```toml
lira_version = 2024
call_timeout_s = 120
```

## Файлы сервера

| Что | Где |
|---|---|
| Журнал | `%APPDATA%\lira-sapr-mcp\server.log` |
| Резервные копии моделей | `lira-mcp-backups\` рядом с моделью, одна копия на файл за сессию |
| Временные текстовые файлы | при импорте — временная папка Windows; при выгрузке — папка текстовых данных ЛИРЫ (`TextDataDirectory`). Удаляются сразу, одноимённый файл пользователя возвращается на место |
| Результаты и протокол расчёта | рабочая папка ЛИРЫ (`WorkDirectory`), пишет сама ЛИРА |

Папки ЛИРЫ сервер берёт из реестра:
`HKCU\Software\LIRA SAPR\LIRA SAPR 2024\Directories`.

## Проверки

| Команда | Что проверяет |
|---|---|
| `uv run pytest` | модульные тесты без ЛИРЫ (их же запускает хук перед коммитом) |
| `uv run pytest -m lira` | тесты на живой ЛИРЕ: запускает её, работает только с моделями в `tests/live/_work` |
| `uv run ruff check`, `uv run ruff format` | стиль и ошибки кода |
| `uv run zensical build --strict` | сайт документации без битых ссылок |
| `uv run zensical serve -a localhost:8010` | просмотр документации (порт 8000 на машине владельца занят) |

## Если что-то не работает

- **«No supported LIRA-SAPR installation»** — ЛИРА 2024 R2+ не найдена в реестре.
  Проверьте, что она установлена для этого пользователя Windows, или задайте
  `lira_version`.
- **«Could not start LIRA»** — ЛИРА не запускается через COM: запустите её вручную и
  проверьте лицензию.
- **«LIRA did not answer within N s»** — в ЛИРЕ, скорее всего, открыто модальное окно.
  Закройте его вручную; инструменты для окон появятся на этапе 3.
- **«No analysis results»** — модель не рассчитана или рассчитана под другим именем.
- Подробности любой ошибки — в журнале `server.log`.
