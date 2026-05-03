import json
import re
import requests
from PySide6.QtCore import QObject, Signal, QThread

class LLMWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, url, model, messages, timeout=30):
        super().__init__()
        self.url = url
        self.model = model
        self.messages = messages
        self.timeout = timeout

    def run(self):
        try:
            payload = {
                "model": self.model,
                "messages": self.messages,
                "temperature": 0.1,
                "max_tokens": 1024,
                # "response_format": {"type": "json_object"} # Often causes 400 in older/specific LM Studio builds
            }
            response = requests.post(f"{self.url}/v1/chat/completions", json=payload, timeout=self.timeout)
            
            if response.status_code != 200:
                self.error.emit(f"LM Studio Error {response.status_code}: {response.text}")
                return

            data = response.json()
            content = data['choices'][0]['message']['content'].strip()
            
            # --- HIGH-RESILIENCE DEEP RECOVERY PARSER ---
            parsed_json = None
            
            # 1. Try the ideal block extraction
            match = re.search(r'(\{.*\})', content, re.DOTALL)
            if match:
                try:
                    parsed_json = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            # 2. If blocked or truncated, attempt structure repair
            if not parsed_json:
                start_idx = content.find('{')
                if start_idx != -1:
                    partial = content[start_idx:]
                    # Iteratively try closing the structure with common JSON endings
                    endings = ["}", "]}", "}]}", "}}"]
                    for end in endings:
                        for i in range(1, 3):
                            try:
                                parsed_json = json.loads(partial + (end * i))
                                break
                            except: continue
                        if parsed_json: break
            
            # 3. Final Fallback: Emit reasoning even if commands are lost
            if parsed_json:
                self.finished.emit(parsed_json)
            else:
                self.finished.emit({"reasoning": content, "commands": []})
            # ---------------------------------------------
            
        except requests.exceptions.RequestException as e:
            self.error.emit(f"Network Error: {str(e)}")
        except json.JSONDecodeError as e:
            self.error.emit(f"JSON Parse Error: {str(e)} | Content: {content[:100]}...")
        except Exception as e:
            self.error.emit(f"Unexpected Error: {str(e)}")


class TacticalLLMClient(QObject):
    response_received = Signal(dict)
    error_received = Signal(str)
    models_updated = Signal(list)

    def __init__(self, base_url="http://192.168.1.122:1234"):
        super().__init__()
        self.base_url = base_url
        self.system_prompt = """You are a Tactical Flight Commander AI for TrueGCS. 
Your job is to translate the human operator's natural language requests into structured flight commands.

You must ALWAYS respond with a JSON object in exactly this format:
{
  "reasoning": "Briefly explain what you are doing.",
  "commands": [
    {
      "action": "takeoff",
      "target_id": "1:1",
      "altitude": 50.0
    },
    {
      "action": "mission",
      "target_id": "1:1",
      "waypoints": [
        {"lat": -35.0, "lon": 149.0, "alt": 50.0, "speed": 15.0}
      ]
    },
    {
      "action": "rtl",
      "target_id": "1:1"
    },
    {
      "action": "land",
      "target_id": "1:1"
    },
    {
      "action": "locate",
      "target_id": "1:1",
      "x_pct": 0.5,
      "y_pct": 0.5
    }
  ]
}

Available Actions:
- "takeoff": requires "target_id" and "altitude" (float).
- "auto": requires "target_id" (starts the mission).
- "mission": requires "target_id" and "waypoints" (a list of objects with lat, lon, alt, speed).
- "rtl": requires "target_id" (Return to Launch / Home).
- "land": requires "target_id" (Land at current position).
- "locate": requires "target_id", "x_pct", "y_pct" (float between 0.0-1.0, 0,0=top-left, 1,1=bottom-right). Use this if an image is provided to locate a requested target.

Tactical Landmarks (Relative to Home):
- "Red Rock River": (Search pattern near current position)
- "Base Alpha": (Current Home / Launch Point)
- "North Corner": (100m North of current position)

Notes:
- If a landmark is mentioned, calculate waypoints relative to the CURRENT FLEET STATUS provided in the prompt.
- If a location is unknown, explain this to the operator and ask for coordinates or a map click.
- Return ONLY the JSON object. Do not add conversational text or markdown."""
        
        self.chat_history = [{"role": "system", "content": self.system_prompt}]
        self.current_worker = None

    def fetch_models(self, url=None):
        """Fetches available models from LM Studio asynchronously to avoid freezing UI."""
        if url:
            self.base_url = url
            
        class ModelFetcher(QThread):
            models_fetched = Signal(list)
            fetch_error = Signal(str)
            
            def __init__(self, url):
                super().__init__()
                self.url = url
                
            def run(self):
                try:
                    res = requests.get(f"{self.url}/v1/models", timeout=5)
                    res.raise_for_status()
                    models = [m['id'] for m in res.json().get('data', [])]
                    self.models_fetched.emit(models)
                except Exception as e:
                    self.fetch_error.emit(str(e))
                    
        self.fetcher = ModelFetcher(self.base_url)
        self.fetcher.models_fetched.connect(self.models_updated.emit)
        self.fetcher.fetch_error.connect(self.error_received.emit)
        self.fetcher.start()

    def send_prompt(self, user_text, model_name, url=None, image_b64=None):
        if url:
            self.base_url = url
            
        if self.current_worker and self.current_worker.isRunning():
            self.error_received.emit("Still waiting for previous response...")
            return

        # Add user prompt to history
        if image_b64:
            self.chat_history.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            })
        else:
            self.chat_history.append({"role": "user", "content": user_text})
        
        # We only keep the system prompt and the last couple interactions to save context.
        # Strip image payloads from older history entries to avoid context bloat 🖼️
        if len(self.chat_history) > 7:
            self.chat_history = [self.chat_history[0]] + self.chat_history[-6:]
        for msg in self.chat_history[:-1]:  # Never strip the current message
            if isinstance(msg.get("content"), list):
                # Replace image content with a text-only summary to save tokens
                msg["content"] = [p for p in msg["content"] if p.get("type") == "text"]
                if not msg["content"]:
                    msg["content"] = "[image - pruned from history]"

        # Use a longer timeout for vision requests — 31B VLMs are slow on images
        timeout = 120 if image_b64 else 30
        self.current_worker = LLMWorker(self.base_url, model_name, self.chat_history, timeout=timeout)
        self.current_worker.finished.connect(self._on_finished)
        self.current_worker.error.connect(self._on_error)
        self.current_worker.start()

    def _on_finished(self, response_dict):
        # Add assistant response to history
        self.chat_history.append({"role": "assistant", "content": json.dumps(response_dict)})
        self.response_received.emit(response_dict)

    def _on_error(self, error_msg):
        # Remove the failed user prompt so they can try again
        if self.chat_history[-1]["role"] == "user":
            self.chat_history.pop()
        self.error_received.emit(error_msg)
