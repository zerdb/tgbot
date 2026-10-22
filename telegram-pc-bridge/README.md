# Telegram PC Bridge v2

Локальный Tkinter-пульт управления Windows/ПК через Telegram. Управление построено на явном allow-list: бот не принимает произвольные PowerShell/CMD-команды и не выполняет произвольный Python-код.

## Панель Telegram

После запуска бот присылает inline-панель:

- 🖥 ПК — статус, скриншот, блокировка.
- 📊 Мониторинг — процессы, диски, сеть, GPU.
- 📁 Файлы — Desktop, Downloads, Documents.
- 🪟 Окна — список окон, сворачивание, выход из Windows.
- 📱 Приложения — Notepad, Calculator, Explorer.
- 🧰 Проекты — запуск заранее известных проектов из репозитория.
- ⚙️ Система — clipboard, разрешённые hotkeys, allow-list служб.
- 📋 Журнал — локальный журнал Tkinter.

Опасные действия (\`lock\`, \`minimize_all\`, \`logoff\`) требуют второй кнопки ⚠️ Подтвердить.

## Разрешённые действия

- \`/status\`, \`/processes\`, \`/drives\`, \`/network\`, \`/gpu\`
- \`/windows\`, \`/lock\`, \`/minimize_all\`, \`/logoff\`
- \`/run <allow-list app>\`, \`/stop <allow-list app>\`
- \`/files <desktop|downloads|documents>\`
- \`/screenshot\`
- \`/clip_get\`, \`/clip_set <text>\`
- \`/hotkey <allow-list>\`
- \`/projects\`, \`/project <allow-list project>\`
- \`/services\`
- \`/download <desktop/...|downloads/...|documents/...>\`
- Telegram upload → только в локальную папку \`telegram-pc-bridge/downloads/\`

## Allow-list

### Приложения
\`notepad\`, \`calculator\`, \`explorer\`

### Hotkeys
\`ctrl_c\`, \`ctrl_v\`, \`ctrl_s\`, \`ctrl_w\`, \`alt_tab\`, \`ctrl_shift_esc\`, \`win_d\`

### Windows services
\`spooler\`, \`w32time\`, \`bits\`

### Проекты
Проекты определяются из фиксированного списка директорий репозитория. Произвольный путь к \`.exe\`, \`.py\`, \`.bat\` или PowerShell не принимается.

### Файлы
Удалённая отправка разрешена только из \`Desktop\`, \`Downloads\`, \`Documents\`. Обход родительских директорий блокируется.

## Зависимости

\`\`\`bash
pip install -r requirements.txt
\`\`\`

## Запуск

\`\`\`bash
python main.py
\`\`\`

Перед работой укажи свой Telegram User ID. Команды от других пользователей блокируются.

Токен и User ID сохраняются в локальном \`config.json\`, который не должен попадать в Git.
