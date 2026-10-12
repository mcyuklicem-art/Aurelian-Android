# AURELIAN — Android Telegram Workspace

Modern, dark-themed Kivy Android client built around the user-supplied `zz.py` workflow. It includes account profiles, Telegram code/2FA login, group discovery and filtering, message pool, interval setting, one-shot sending, stop control, and basic stats.

## Build APK in the cloud (phone-friendly)
1. Upload this folder to a GitHub repository.
2. Open **Actions → Build AURELIAN APK → Run workflow**.
3. When it completes, open the run and download the `aurelian-debug-apk` artifact.

The workflow builds a **debug APK**. It has not been built or device-tested in this workspace. Test it on your own device before distributing it; a production release needs a signing key and privacy/security review.

## Requirements
- Android 8.0+ (API 26+)
- Telegram API ID and API Hash from https://my.telegram.org
- Network access

## Safety and privacy
- Telegram sessions are stored in the app-private directory. Do not share session files, API hashes, or login codes.
- Sending is user-initiated, one-shot, and capped at 20 selected groups per operation. No hidden anti-detection jitter or unattended infinite sending loop is included.
- Telegram FloodWait is respected by stopping the send operation.
- Do not use this application for unsolicited bulk messages. Follow Telegram rules and the consent expectations of each group.
- The original `zz.py` contains a hardcoded Telegram bot token. Revoke/regenerate that token in BotFather before using the old bot again; never commit secrets to a public repository.

## Notes
The original source is a Telegram bot UI, not an Android UI. This project recreates the core user workflow in a native-feeling Android interface; it is not byte-for-byte identical. The debug APK build and real-device compatibility must be verified before customer delivery.
