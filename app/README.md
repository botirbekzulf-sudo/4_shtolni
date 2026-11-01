# Сборка приложений

Сборка идёт на GitHub, ничего устанавливать на компьютер не нужно. Папки `app` и `.github` и файл `index.html` должны лежать в корне репозитория.

После загрузки в ветку `main` откройте вкладку **Actions**. Готовые файлы лежат внизу страницы сборки:

- `android-test-apk`: APK для установки на свой телефон
- `android-play-aab`: файл для Google Play
- `windows-exe`: установщик и переносимая версия для Windows

## Подпись для Google Play

1. Установите JDK 21 (например, Temurin) и создайте ключ:

   ```bash
   keytool -genkeypair -v -keystore upload.jks -alias upload -keyalg RSA -keysize 2048 -validity 10000
   ```

2. Сохраните `upload.jks` и пароли в надёжном месте. Никогда не загружайте этот файл в репозиторий.
3. Получите текст ключа в PowerShell:

   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("upload.jks")) | Set-Clipboard
   ```

4. В репозитории откройте Settings → Secrets and variables → Actions и добавьте секреты:
   `ANDROID_KEYSTORE_BASE64`, `ANDROID_STORE_PASSWORD`, `ANDROID_KEY_ALIAS` (`upload`), `ANDROID_KEY_PASSWORD`.

Без секретов AAB собирается без подписи, и Google Play его не примет.

Идентификатор приложения `com.botirbekzulf.chetyreshtolni` задан в `capacitor.config.json` и `package.json`. После первой публикации его изменить нельзя.
