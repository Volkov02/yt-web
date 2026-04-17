# yt-web

Простой веб-интерфейс для [yt-dlp](https://github.com/yt-dlp/yt-dlp) на Flask. Позволяет скачивать видео и аудио с YouTube и других сайтов через браузер, не трогая командную строку.

## Возможности

- Скачивание видео в выбранном качестве
- Извлечение аудио (MP3)
- Прогресс-бар в реальном времени (через Server-Sent Events)
- Упаковка в exe через PyInstaller (`build.bat`)
- ffmpeg подтягивается автоматически через `imageio-ffmpeg`

## Установка

Требуется **Python 3.9+**.

```bash
pip install -r requirements.txt
python app.py
```

Откроется браузер на `http://localhost:5000`.

## Запуск на Windows

```cmd
run.bat
```

## Сборка в exe

```cmd
build.bat
```

Результат — в папке `dist/`.

## Зависимости

- `flask>=3.0.0`
- `yt-dlp>=2024.1.0`
- `imageio-ffmpeg>=0.4.9`
