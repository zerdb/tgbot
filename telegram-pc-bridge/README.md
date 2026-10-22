# Telegram PC Bridge

Локальный Tkinter-пульт управления ПК через Telegram. Все действия построены на явном **allow-list**.

## Команды

- `/status` — подробный статус ПК.
- `/apps` — разрешённые приложения.
- `/run notepad`, `/run calculator`, `/run explorer` — запуск только разрешённых приложений.
- `/stop notepad`, `/stop calculator`, `/stop explorer` — остановка только разрешённых приложений.
- `/files desktop`, `/files downloads`, `/files documents` — список разрешённых папок.
- `/processes` — топ-20 процессов по RAM.
- `/lock` — блокировка Windows.
- `/minimize_all` — свернуть окна.
- `/help` — справка.

Произвольные PowerShell/CMD-команды, произвольный Python-код, произвольные PID и произвольные пути для выполнения не поддерживаются.

## Установка

```bash
pip install -r requirements.txt
python main.py
```

Токен и User ID хранятся локально в `config.json`, который исключён из Git.
