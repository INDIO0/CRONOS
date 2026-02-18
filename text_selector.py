"""
Text Selection Reader - Crono
Detecta texto selecionado e l automaticamente
"""

import threading
import time
import pyperclip
from typing import Optional, Callable
import asyncio


class TextSelectionReader:
    """Detecta e l texto selecionado com mouse"""
    
    def __init__(self):
        self.last_clipboard = ""
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.on_text_selected: Optional[Callable[[str], None]] = None
        self.check_interval = 0.3  # Verificar a cada 300ms
        self.min_text_length = 2  # Mnimo de caracteres
        
    def start_monitoring(self):
        """Inicia monitoramento de texto selecionado"""
        if self.monitoring:
            return
            
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print(" Monitoramento de seleo ativado")
        
    def stop_monitoring(self):
        """Para monitoramento"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        print("  Monitoramento de seleo desativado")
        
    def _monitor_loop(self):
        """Loop de monitoramento em thread separada"""
        while self.monitoring:
            try:
                # Tentar copiar texto selecionado
                self._check_selected_text()
            except Exception as e:
                pass
            
            time.sleep(self.check_interval)
    
    def _check_selected_text(self):
        """Verifica se h novo texto selecionado"""
        try:
            import subprocess
            
            # Usar PowerShell para copiar seleo (Windows)
            script = """
            Add-Type -Assembly System.Windows.Forms
            
            $clipboard_before = [System.Windows.Forms.Clipboard]::GetText()
            
            # Simular Ctrl+C para copiar seleo
            [System.Windows.Forms.SendKeys]::SendWait('^c')
            
            Start-Sleep -Milliseconds 100
            
            $clipboard_after = [System.Windows.Forms.Clipboard]::GetText()
            
            if ($clipboard_after -and $clipboard_after -ne $clipboard_before) {
                Write-Output $clipboard_after
            }
            """
            
            # Executar script PowerShell
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            selected_text = result.stdout.strip()
            
            if selected_text and len(selected_text) >= self.min_text_length:
                if selected_text != self.last_clipboard:
                    self.last_clipboard = selected_text
                    
                    # Chamar callback se registrado
                    if self.on_text_selected:
                        self.on_text_selected(selected_text)
                        
        except Exception as e:
            pass


class SimpleTextReader:
    """Verso mais simples usando clipboard direto"""
    
    def __init__(self):
        self.last_clipboard = ""
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.on_text_copied: Optional[Callable[[str], None]] = None
        self.check_interval = 0.2
        self.min_text_length = 2
        
    def start_monitoring(self):
        """Inicia monitoramento"""
        if self.monitoring:
            return
            
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print(" Leitor de seleo ativado")
        
    def stop_monitoring(self):
        """Para monitoramento"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        print("  Leitor de seleo desativado")
        
    def _monitor_loop(self):
        """Loop de verificao"""
        last_check = time.time()
        
        while self.monitoring:
            try:
                # Verificar clipboard periodicamente
                current_clip = pyperclip.paste()
                
                # Se mudou e no  vazio
                if current_clip and current_clip != self.last_clipboard:
                    # Verificar se  texto novo (no  muito comprido de mais)
                    if len(current_clip) < 5000 and len(current_clip) >= self.min_text_length:
                        # Evitar duplicatas
                        if current_clip.strip() != self.last_clipboard.strip():
                            self.last_clipboard = current_clip
                            # Chamar callback quando texto  copiado
                            if self.on_text_copied:
                                self.on_text_copied(current_clip)
                
            except Exception as e:
                pass
            
            time.sleep(self.check_interval)
    
    def get_last_selected(self) -> str:
        """Retorna o ltimo texto copiado"""
        return self.last_clipboard
    
    def clear_last_selected(self):
        """Limpa o texto copiado"""
        self.last_clipboard = ""


class WindowsTextSelector:
    """Detector avanado para Windows usando UI Automation"""
    
    def __init__(self):
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.on_text_selected: Optional[Callable[[str], None]] = None
        self.last_selected = ""
        self.check_interval = 0.2
        
    def start_monitoring(self):
        """Inicia monitoramento"""
        if self.monitoring:
            return
            
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print(" Detector Windows ativado")
        
    def stop_monitoring(self):
        """Para monitoramento"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        print("  Detector Windows desativado")
    
    def get_last_selected(self) -> str:
        """Retorna o ltimo texto selecionado"""
        return self.last_selected
    
    def clear_last_selected(self):
        """Limpa o texto selecionado"""
        self.last_selected = ""
    
    def _monitor_loop(self):
        """Loop de monitoramento"""
        while self.monitoring:
            try:
                # Simular Ctrl+C para copiar seleo
                import subprocess
                subprocess.run(
                    ["powershell", "-Command", "[System.Windows.Forms.SendKeys]::SendWait('^c')"],
                    capture_output=True,
                    timeout=0.5
                )
                
                time.sleep(0.05)
                
                # Ler do clipboard
                try:
                    selected = pyperclip.paste()
                    
                    if selected and selected != self.last_selected:
                        if len(selected) >= 2 and len(selected) < 5000:
                            self.last_selected = selected
                            
                            if self.on_text_selected:
                                self.on_text_selected(selected)
                except:
                    pass
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                pass


# Global instance
_reader = None

def get_text_reader():
    """Retorna instncia global do leitor"""
    global _reader
    if _reader is None:
        try:
            _reader = WindowsTextSelector()
        except:
            try:
                _reader = SimpleTextReader()
            except:
                _reader = SimpleTextReader()
    return _reader


def start_text_selection_reader():
    """Inicia o leitor de seleo de texto"""
    reader = get_text_reader()
    reader.start_monitoring()
    return reader


def stop_text_selection_reader():
    """Para o leitor de seleo de texto"""
    reader = get_text_reader()
    reader.stop_monitoring()
