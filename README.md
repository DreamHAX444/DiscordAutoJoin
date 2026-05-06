# Discord Auto-Join Bot v2.0

A powerful, persistent Windows background application that automatically joins a specific Discord voice channel, enables the camera, and ensures your connection stays alive.

## 🚀 Features

- **Automated Voice Connection:** Automatically navigates to a Discord channel and joins voice.
- **Camera Automation:** Silent re-enabling of camera if it's turned off.
- **Microphone Management:** Ensures the microphone is muted upon joining (customizable).
- **Persistent Monitoring:** Continually checks connection status and auto-reconnects if dropped.
- **System Tray Integration:** Runs silently in the background with a diagnostic tray icon.
- **Windows Startup Support:** Registers itself to start automatically when Windows boots.
- **Memory Optimized:** Uses custom Chrome arguments to minimize RAM usage.

## 🛠️ Technology Stack

- **Python:** Core logic and automation.
- **Playwright:** Browser automation for interacting with the Discord web client.
- **PyStray:** System tray icon and menu management.
- **Pillow:** Dynamic icon generation.

## 📦 Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd DiscordAutoJoin
   ```

2. Install dependencies:
   ```bash
   pip install playwright pystray pillow
   playwright install chromium
   ```

3. Configure the `DISCORD_URL` in `main.py` to your desired voice channel.

4. Run the application:
   ```bash
   python DiscordAutoJoin/main.py
   ```

## 🖥️ Usage

- **First Run:** On the first launch, the app will wait for you to log into Discord manually in the opened Chrome window. Once logged in, right-click the tray icon and select **"First-Run Done"**.
- **Background Mode:** The app will minimize to the system tray and monitor your connection in the background.
- **Logs:** Logs are stored in `%APPDATA%/DiscordAutoJoin/app.log`.

## 🛡️ License

This project is for educational purposes. Use responsibly and adhere to Discord's Terms of Service.
