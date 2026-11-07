
import os
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from PIL import Image, ImageGrab
import pygetwindow as gw
from pynput import keyboard
from google import genai
from google.genai import types

CONFIG_FILE = "config.json"
CANDIDATE_MODELS = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash"]
HOTKEY = "<ctrl>+<alt>+a"
FREE_TIER_TPM_LIMIT = 250000


class GeminiAssistantApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gemini Screen & Chat Assistant")
        self.root.geometry("680x720")
        self.root.attributes("-topmost", True)

        self.client = None
        self.selected_file_path = None
        self.is_processing = False

        self.token_log = []
        self.chat_history = []

        self.selected_model_var = tk.StringVar(value=CANDIDATE_MODELS[0])

        self._build_ui()
        self._auto_load_key()
        self._start_hotkey_listener()
        self._start_token_ticker()

    def _build_ui(self):
        top_frame = ttk.LabelFrame(self.root, text=" Settings & Model Selection ", padding=10)
        top_frame.pack(fill="x", padx=10, pady=5)

        # Row 0: API Key Entry
        ttk.Label(top_frame, text="API Key:").grid(row=0, column=0, sticky="w")
        self.api_key_entry = ttk.Entry(top_frame, show="*")
        self.api_key_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(top_frame, text="Save Key", command=self.save_key_action).grid(row=0, column=2, padx=5)

        # Row 0 (Right): Active Model Selector Dropdown
        ttk.Label(top_frame, text="Active Model:").grid(row=0, column=3, sticky="w", padx=(15, 5))
        self.model_dropdown = ttk.Combobox(
            top_frame, 
            textvariable=self.selected_model_var, 
            values=CANDIDATE_MODELS, 
            state="readonly", 
            width=20
        )
        self.model_dropdown.grid(row=0, column=4, sticky="e", padx=5)

        top_frame.columnconfigure(1, weight=1)

        # Row 1: Real-time Token Tracker Display
        self.token_status_var = tk.StringVar(value="Est. Quota: 250,000 / 250,000 tokens available (100%)")
        token_label = ttk.Label(top_frame, textvariable=self.token_status_var, font=("Segoe UI", 9, "bold"), foreground="#0066cc")
        token_label.grid(row=1, column=0, columnspan=5, sticky="w", pady=(8, 0))

        # Action Bar Frame
        action_frame = ttk.Frame(self.root, padding=5)
        action_frame.pack(fill="x", padx=10)

        self.btn_capture = ttk.Button(
            action_frame, 
            text=f"📸 Capture Active Window ({HOTKEY})", 
            command=self.trigger_capture
        )
        self.btn_capture.pack(side="left", fill="x", expand=True, padx=2)

        # Chat Log Box
        chat_frame = ttk.LabelFrame(self.root, text=" Conversation ", padding=10)
        chat_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.chat_display = scrolledtext.ScrolledText(chat_frame, wrap="word", state="disabled")
        self.chat_display.pack(fill="both", expand=True)

        self.file_label = ttk.Label(self.root, text="No file attached", foreground="gray")
        self.file_label.pack(anchor="w", padx=15)

        # Input & Controls Frame
        input_frame = ttk.Frame(self.root, padding=10)
        input_frame.pack(fill="x", padx=5, pady=5)

        self.user_input = ttk.Entry(input_frame)
        self.user_input.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.user_input.bind("<Return>", lambda e: self.send_text_message())

        ttk.Button(input_frame, text="📎 Attach", command=self.attach_file).pack(side="left", padx=2)
        ttk.Button(input_frame, text="❌ Clear File", command=self.clear_attachment).pack(side="left", padx=2)
        ttk.Button(input_frame, text="🗑️ Clear Chat", command=self.clear_chat).pack(side="left", padx=2)
        
        self.btn_send = ttk.Button(input_frame, text="Send", command=self.send_text_message)
        self.btn_send.pack(side="left", padx=2)

        # Status Bar
        self.status_var = tk.StringVar(value="Ready.")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.pack(side="bottom", fill="x")

    def _start_token_ticker(self):
        self._refresh_token_display()
        self.root.after(1000, self._start_token_ticker)

    def _refresh_token_display(self):
        now = time.time()
        self.token_log = [(t, count) for t, count in self.token_log if now - t < 60]
        used_tokens = sum(count for _, count in self.token_log)
        remaining_tokens = max(0, FREE_TIER_TPM_LIMIT - used_tokens)
        percentage = int((remaining_tokens / FREE_TIER_TPM_LIMIT) * 100)
        self.token_status_var.set(
            f"Est. Quota: {remaining_tokens:,} / {FREE_TIER_TPM_LIMIT:,} tokens left ({percentage}% available)"
        )

    def record_token_usage(self, token_count: int):
        if token_count > 0:
            self.token_log.append((time.time(), token_count))
            self.root.after(0, self._refresh_token_display)

    def _auto_load_key(self):
        saved_key = ""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    saved_key = data.get("GEMINI_API_KEY", "")
            except Exception:
                pass
        if not saved_key:
            saved_key = os.environ.get("GEMINI_API_KEY", "")

        if saved_key:
            self.api_key_entry.delete(0, "end")
            self.api_key_entry.insert(0, saved_key)
            self._init_client(saved_key)

    def save_key_action(self):
        key = self.api_key_entry.get().strip()
        if not key:
            self.status_var.set("Please enter a valid API key.")
            return
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"GEMINI_API_KEY": key}, f)
            self._init_client(key)
            self._append_log("System", "API key saved locally.")
        except Exception as e:
            self.status_var.set(f"Failed to save key file: {e}")

    def _init_client(self, api_key: str = None):
        if not api_key:
            api_key = self.api_key_entry.get().strip()
        if api_key:
            try:
                self.client = genai.Client(api_key=api_key)
                self.status_var.set("API Client ready.")
                self._append_log("System", "Gemini Client successfully initialized!")
            except Exception as e:
                self.status_var.set("Initialization Error.")
                self._append_log("System", f"Fatal Setup Error: {e}")
        else:
            self.status_var.set("Please enter your Gemini API Key.")

    def _start_hotkey_listener(self):
        def on_hotkey():
            self.root.after(0, self.trigger_capture)
        try:
            listener = keyboard.GlobalHotKeys({HOTKEY: on_hotkey})
            listener.daemon = True
            listener.start()
        except Exception as e:
            self._append_log("System", f"Hotkey Registration Failed: {e}")

    def _append_log(self, sender: str, message: str):
        self.chat_display.config(state="normal")
        self.chat_display.insert("end", f"[{sender}]: {message}\n\n")
        self.chat_display.see("end")
        self.chat_display.config(state="disabled")

    def attach_file(self):
        file_path = filedialog.askopenfilename(
            title="Select File",
            filetypes=[("Supported Files", "*.png *.jpg *.jpeg *.pdf *.txt"), ("All Files", "*.*")]
        )
        if file_path:
            self.selected_file_path = file_path
            self.file_label.config(text=f"Attached: {os.path.basename(file_path)}", foreground="green")
        else:
            self.clear_attachment()

    def clear_attachment(self):
        self.selected_file_path = None
        self.file_label.config(text="No file attached", foreground="gray")
        self.status_var.set("Attachment cleared.")

    def clear_chat(self):
        self.chat_history = []
        self._append_log("System", "Chat history memory wiped.")
        self.status_var.set("Chat memory cleared.")

    def capture_active_window(self) -> Image.Image:
        windows = gw.getAllWindows()
        target_win = None
        for w in windows:
            if w.isActive and "Gemini Screen & Chat Assistant" not in w.title and w.title != "":
                target_win = w
                break
        if not target_win:
            target_win = gw.getActiveWindow()
        if not target_win or target_win.isMinimized:
            return None

        bbox = (target_win.left, target_win.top, target_win.left + target_win.width, target_win.top + target_win.height)
        img = ImageGrab.grab(bbox=bbox)
        
        max_dim = 800
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        return img

    def trigger_capture(self):
        if self.is_processing:
            return
        
        if not self.client:
            self._init_client()
            if not self.client:
                self._append_log("System", "Error: Gemini client is not initialized.")
                return

        self.is_processing = True
        self.btn_capture.config(state="disabled")
        self.btn_send.config(state="disabled")

        prompt = self.user_input.get().strip()
        if not prompt:
            prompt = "Analyze the content on this screen, and if there are questions, give me the answer directly"
        self.user_input.delete(0, "end")
        self.status_var.set("Capturing active window...")

        self.root.attributes("-topmost", False)
        time.sleep(0.2)
        image = self.capture_active_window()
        self.root.attributes("-topmost", True)

        if image is None:
            self.status_var.set("Error: Could not capture active window.")
            self._reset_ui_lock()
            return

        self._append_log("User", f"[Screen Capture Sent] {prompt}")
        threading.Thread(target=self._query_gemini_and_cleanup, args=([prompt, image], None), daemon=True).start()

    def send_text_message(self):
        if self.is_processing:
            return

        if not self.client:
            self._init_client()
            if not self.client:
                self._append_log("System", "Error: Gemini client is not initialized.")
                return

        prompt = self.user_input.get().strip()
        if not prompt and not self.selected_file_path:
            return

        self.is_processing = True
        self.btn_capture.config(state="disabled")
        self.btn_send.config(state="disabled")

        self.user_input.delete(0, "end")
        contents = []
        file_msg = ""
        uploaded_file_ref = None

        if self.selected_file_path:
            filename = os.path.basename(self.selected_file_path)
            file_msg = f" [Attached: {filename}]"
            self.status_var.set(f"Uploading & processing {filename}...")
            try:
                uploaded_file_ref = self.client.files.upload(file=self.selected_file_path)
                while uploaded_file_ref.state.name == "PROCESSING":
                    time.sleep(1)
                    uploaded_file_ref = self.client.files.get(name=uploaded_file_ref.name)
                contents.append(uploaded_file_ref)
            except Exception as e:
                self._append_log("System", f"File Upload Error: {e}")
                self._reset_ui_lock()
                return
            self.clear_attachment()

        if prompt:
            contents.append(prompt)

        self._append_log("User", f"{prompt}{file_msg}")
        threading.Thread(target=self._query_gemini_and_cleanup, args=(contents, uploaded_file_ref), daemon=True).start()

    def _query_gemini_and_cleanup(self, contents: list, file_ref=None):
        try:
            self._query_gemini(contents)
        finally:
            if file_ref and self.client:
                try:
                    self.client.files.delete(name=file_ref.name)
                except Exception:
                    pass
            self.root.after(0, self._reset_ui_lock)

    def _reset_ui_lock(self):
        self.is_processing = False
        self.btn_capture.config(state="normal")
        self.btn_send.config(state="normal")
        self.status_var.set("Ready.")

    def _query_gemini(self, contents: list):
        self.status_var.set("Querying Gemini AI...")

        request_contents = self.chat_history.copy() + contents
        chosen_model = self.selected_model_var.get()
        models_to_try = [chosen_model] + [m for m in CANDIDATE_MODELS if m != chosen_model]

        for model in models_to_try:
            try:
                response = self.client.models.generate_content(model=model, contents=request_contents)
                
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    prompt_tokens = response.usage_metadata.prompt_token_count or 0
                    cand_tokens = response.usage_metadata.candidates_token_count or 0
                    total_used = prompt_tokens + cand_tokens
                    self.record_token_usage(total_used)
                    self._append_log("System", f"[{model}] Request used ~{total_used:,} tokens")

                self._append_log("Gemini", response.text)

                # Extracts text prompts safely, replacing binary image/file objects with a clean tag
                text_parts = [item for item in contents if isinstance(item, str)]
                has_media = any(not isinstance(item, str) for item in contents)
                
                if text_parts:
                    user_text = " ".join(text_parts) + (" [Attached image/file analyzed]" if has_media else "")
                else:
                    user_text = "[User provided an image or file attachment]"

                self.chat_history.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=user_text)])
                )
                self.chat_history.append(
                    types.Content(role="model", parts=[types.Part.from_text(text=response.text)])
                )

                if len(self.chat_history) > 10:
                    self.chat_history = self.chat_history[-10:]

                return

            except Exception as e:
                err = str(e)
                if "10053" in err or "aborted" in err:
                    self._append_log("System", "[WinError 10053] Local network connection dropped.")
                    return
                elif "404" in err:
                    self._append_log("System", f"Model '{model}' not found. Trying fallback...")
                    continue
                elif "503" in err or "UNAVAILABLE" in err:
                    self._append_log("System", f"Model '{model}' busy (503). Retrying in 3s...")
                    time.sleep(3)
                    continue
                elif "429" in err or "RESOURCE_EXHAUSTED" in err:
                    self._append_log("System", "Rate limit hit (429). Waiting for server cooldown.")
                    return
                else:
                    self._append_log("System", f"Model {model} Error: {e}")
                    break

if __name__ == "__main__":
    root = tk.Tk()
    app = GeminiAssistantApp(root)
    root.mainloop()