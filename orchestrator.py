"""
JARVIS - Simple Voice Assistant
"""
import os
import sys
import asyncio
from dotenv import load_dotenv
from actions.open_app import open_app
from actions.close_app import close_app
from actions.weather_report import weather_action
from actions.screen_vision import capture_and_analyze_screen
from actions.type_text import type_text_action
from actions.file_operations import file_operations
from actions.project_manager import project_manager
from actions.screen_control import screen_controller
from actions.keyboard_control import press_key_action
from actions.open_website import open_website_action

load_dotenv()


class CronoOrchestrator:
    """
    Simple orchestration for voice commands.
    """\
    
    def __init__(self):
        self.running = True
        self.ui = None
    
    def log(self, message: str):
        print(f"[ORCHESTRATOR] {message}")
    
    def set_ui(self, ui):
        self.ui = ui
    
    async def process_command(self, text: str):
        """
        Process voice command and execute appropriate action.
        """
        if not text:
            return
        
        self.log(f"Processing: {text}")
        
        # Simple command parsing (can be enhanced with LLM)
        text_lower = text.lower().strip()
        
        # Check for app opening commands
        if any(x in text_lower for x in ["abra", "abre", "abrir", "open"]):
            # Try to extract app name
            words = text_lower.split()
            for i, word in enumerate(words):
                if word in ["abra", "abre", "abrir", "open"]:
                    if i + 1 < len(words):
                        app_name = words[i + 1]
                        result = open_app({"app_name": app_name}, player=self.ui)
                        if result:
                            return
                    else:
                        if self.ui:
                            self.ui.write_log("Qual aplicativo o senhor gostaria de abrir")
                        return
            
            # If no specific app found, try common apps
            for app in ["chrome", "firefox", "spotify", "vscode", "notepad"]:
                if app in text_lower:
                    open_app({"app_name": app}, player=self.ui)
                    return
            
            if self.ui:
                self.ui.write_log("Desculpe, não entendi qual aplicativo abrir.")
        
        # Check for close app commands
        elif any(x in text_lower for x in ["fecha", "feche", "fechar", "close"]):
            words = text_lower.split()
            for i, word in enumerate(words):
                if word in ["fecha", "feche", "fechar", "close"]:
                    if i + 1 < len(words):
                        app_name = words[i + 1]
                        close_app({"app_name": app_name}, player=self.ui)
                        return
            
            if self.ui:
                self.ui.write_log("Qual aplicativo o senhor gostaria de fechar")
        
        # Check for screen description
        elif any(x in text_lower for x in ["o que você vê", "descreva a tela", "o que tem na tela"]):
            capture_and_analyze_screen(player=self.ui, session_memory=None, user_question=text)
        
        # Check for weather
        elif any(x in text_lower for x in ["clima", "tempo", "previsão", "vai chover"]):
            # Extract city if mentioned
            city = None
            words = text_lower.split()
            for i, word in enumerate(words):
                if word in ["em", "de", "para"]:
                    if i + 1 < len(words):
                        city = words[i + 1].capitalize()
                        break
            
            weather_action({"city": city}, player=self.ui)
        
        # Check for typing
        elif any(x in text_lower for x in ["digite", "digita", "escreva", "type"]):
            # Extract text to type
            text_to_type = text_lower
            for phrase in ["digite", "digita", "escreva", "type"]:
                text_to_type = text_to_type.replace(phrase, "").strip()
            if text_to_type:
                type_text_action({"text": text_to_type}, player=self.ui)
        
        # Check for file operations
        elif any(x in text_lower for x in ["cria arquivo", "crie arquivo", "criar arquivo"]):
            file_operations({"operation": "create_file"}, player=self.ui)
        elif any(x in text_lower for x in ["cria pasta", "crie pasta", "criar pasta"]):
            file_operations({"operation": "create_folder"}, player=self.ui)
        
        # Check for project management
        elif any(x in text_lower for x in ["começa projeto", "novo projeto", "inicia projeto"]):
            project_manager({"action": "create"}, player=self.ui)
        
        # Check for website opening
        elif any(x in text_lower for x in ["abra o site", "vai para", "acesse"]):
            url = None
            words = text_lower.split()
            for i, word in enumerate(words):
                if word in ["site", "para"]:
                    if i + 1 < len(words):
                        url = words[i + 1]
                        break
            if url:
                open_website_action({"url": url}, player=self.ui)
        
        # Check for screen control
        elif any(x in text_lower for x in ["clica", "clique", "click", "mova o mouse"]):
            screen_controller({"target": "elemento", "action_type": "click"}, player=self.ui)
        
        # Check for key press
        elif any(x in text_lower for x in ["pressiona", "aperte", "aperta"]):
            key = "enter"
            if "espaço" in text_lower or "espaco" in text_lower:
                key = "space"
            elif "esc" in text_lower:
                key = "esc"
            press_key_action({"key": key}, player=self.ui)
        
        else:
            if self.ui:
                self.ui.write_log(f"Comando não reconhecido: {text}")
    
    async def run(self):
        """Main orchestration loop"""
        self.ui.write_log("✅ JARVIS Online. Aguardando comandos...")
        
        while self.running:
            try:
                # 1. Get voice input
                # This would be connected to actual STT
                pass
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.log(f"Error: {e}")
                await asyncio.sleep(1)
