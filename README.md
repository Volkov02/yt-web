# yt-web

Простой веб-интерфейс для [yt-dlp](https://github.com/yt-dlp/yt-dlp) на Flask. Позволяет скачивать видео и аудио с YouTube и других сайтов через браузер, не трогая командную строку.

## Возможности

- Скачивание видео в выбранном качестве
- Извлечение аудио (MP3)
- Прогресс-бар в реальном времени (через Server-Sent Events)
- Упаковка в исполняемый файл через PyInstaller (`build.bat` / `build.sh`)
- ffmpeg подтягивается автоматически через `imageio-ffmpeg`

Работает на Windows, Linux и macOS — код кроссплатформенный, платформенная логика (открытие папки, поиск ffmpeg) выбирается автоматически.

## Установка

Требуется **Python 3.9+**.

```bash
pip install -r requirements.txt
python app.py
```

Откроется браузер на `http://127.0.0.1:5757`.

## Запуск

**Windows:**

```cmd
run.bat
```

**Linux / macOS:**

```bash
./run.sh
```

`run.sh` сам создаёт виртуальное окружение `.venv`, ставит зависимости и запускает сервер.

## Сборка в исполняемый файл

**Windows** — результат `dist/YT Downloader.exe`:

```cmd
build.bat
```

**Linux / macOS** — результат `dist/yt-downloader`:

```bash
./build.sh
```

## Зависимости

- `flask>=3.0.0`
- `yt-dlp>=2024.1.0`
- `imageio-ffmpeg>=0.4.9`
