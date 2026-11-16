# Перенос разработки на другой ПК

Распакуйте архив и откройте папку `LocalTransfer` в редакторе. С этой папки запускаются команды для Windows. Состояние на момент переноса — Windows 0.1.3 и Android 0.1.2.

## Windows

Установите Python 3.14 x64. В PowerShell из корня проекта выполните команды.

~~~powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r desktop_win\requirements-dev.lock.txt
.\.venv\Scripts\python.exe -m desktop_win.main
~~~

Если команда `py` недоступна, запустите создание окружения через `python -m venv .venv`, предварительно проверив `python --version`. Файл с зафиксированными версиями включает PyInstaller. Для обычного запуска достаточно Python и зависимостей из `desktop_win/requirements.txt`.

Для сборки установщика дополнительно установите Inno Setup 6. Проверенная версия — 6.7.4. Укажите фактический путь к компилятору.

~~~powershell
.\scripts\build_windows.ps1 -InnoCompiler "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
~~~

Готовый установщик появится в `dist`. [Inno Setup](https://jrsoftware.org/inno-setup/downloads)

## Android

Установите Flutter 3.50.0, Git и Android Studio. Добавьте папку `bin` установленного Flutter в PATH. В SDK Manager установите Android SDK Platform 36, Build-Tools 36.0.0, Platform-Tools, Command-line Tools и NDK (Side by side) 28.2.13676358. Используйте JDK из Android Studio. [Настройка Flutter для Android](https://docs.flutter.dev/platform-integration/android/setup) · [Установка NDK](https://developer.android.com/studio/projects/install-ndk)

~~~powershell
flutter doctor -v
flutter doctor --android-licenses
Set-Location android_app
flutter pub get
flutter analyze
flutter build apk --debug --target-platform android-arm64
~~~

Flutter создаст `android/local.properties` с путями нового ПК. Если используется уже установленный NDK 30.0.16248370, с которым собирался проект на старом ПК, задайте версию в этом локальном файле перед сборкой.

~~~powershell
Add-Content -LiteralPath android\local.properties -Value 'transfer.ndkVersion=30.0.16248370'
~~~

APK появится в `build/app/outputs/flutter-apk/app-debug.apk` внутри `android_app`. Версии пакетов Android сохранены в `pubspec.lock`, а Gradle Wrapper входит в архив.

## Если нужны старые сопряжения

Для продолжения разработки достаточно исходников. Если новый ПК должен сохранить идентификатор прежней установки Windows, устройства и историю, завершите приложение через «Выход» в трее на обоих ПК и перенесите каталог `%LOCALAPPDATA%\LocalTransfer` отдельно. В нём хранится приватный TLS-ключ. Скопируйте его по защищённому каналу. После переноса выберите актуальный интерфейс в списке «Локальная сеть». Полученные файлы хранятся отдельно в `Downloads\Local Transfer`. Старые записи истории могут ссылаться на пути прежнего ПК.

Для установки нового debug APK поверх уже установленной версии на Redmi нужна та же подпись. Отдельно перенесите `%USERPROFILE%\.android\debug.keystore` прежнего ПК в каталог `.android` на новом. Если на новом ПК уже есть debug-ключ, сохраните его копию перед заменой. С другим ключом Android потребует удалить старую версию приложения, при этом локальные данные Android-приложения будут удалены. [Подпись Android-приложений](https://developer.android.com/studio/publish/app-signing)
