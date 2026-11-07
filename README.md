# Gemini Screen & Chat Assistant

A Python desktop application that allows you to capture your active window and chat with Google's Gemini AI about it. It features real-time token tracking and visual context memory.

## Setup
1. Make sure you have Python installed.
2. Install the required dependencies by running:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python app.py
   ```

## Usage
- **API Key:** Paste your Gemini API key in the top bar and click "Save Key". This creates a local `config.json` file on your computer (which is safely ignored by Git).
- **Capture Screen:** Use the `<ctrl>+<alt>+a` hotkey or click the capture button to take a screenshot of your active window and analyze it with Gemini.
- **Chat:** Use the bottom input box to ask follow-up questions or attach other files.
