"""
Memory System for Crono
========================
Sistema de memria que armazena as ltimas 10 mensagens com resumo
e permite recuperar o histrico completo quando solicitado.

Features:
- Armazena as ltimas 10 mensagens com resumo
- Salva histrico completo em JSON
- Permite recuperar contexto quando solicitado
- Integrao com o fluxo existente do Crono
"""

import os
import json
import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

# Configuraes
MEMORY_FILE = "memory_history.json"
MAX_RECENT_MESSAGES = 10

@dataclass
class Message:
    """Representa uma mensagem na memria"""
    id: str
    timestamp: str
    user_text: str
    ai_response: str
    summary: str
    context: str

@dataclass
class MemorySession:
    """Sesso de memria completa"""
    recent_messages: List[Message]
    full_history: List[Message]

class MemorySystem:
    """Sistema de gerenciamento de memria"""

    def __init__(self, memory_file: str = MEMORY_FILE):
        self.memory_file = memory_file
        self.session = self._load_memory()

    def _load_memory(self) -> MemorySession:
        """Carrega a memria do arquivo JSON"""
        if not os.path.exists(self.memory_file):
            return MemorySession(recent_messages=[], full_history=[])

        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return MemorySession(
                    recent_messages=self._deserialize_messages(data.get('recent_messages', [])),
                    full_history=self._deserialize_messages(data.get('full_history', []))
                )
        except Exception as e:
            print(f" Erro ao carregar memria: {e}")
            return MemorySession(recent_messages=[], full_history=[])

    def _save_memory(self):
        """Salva a memria no arquivo JSON"""
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'recent_messages': [asdict(msg) for msg in self.session.recent_messages],
                    'full_history': [asdict(msg) for msg in self.session.full_history]
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f" Erro ao salvar memria: {e}")

    def _deserialize_messages(self, messages: List[Dict[str, Any]]) -> List[Message]:
        """Converte dicionrios para objetos Message"""
        result = []
        for msg in messages:
            try:
                result.append(Message(
                    id=msg['id'],
                    timestamp=msg['timestamp'],
                    user_text=msg['user_text'],
                    ai_response=msg['ai_response'],
                    summary=msg['summary'],
                    context=msg['context']
                ))
            except Exception:
                continue
        return result

    def add_message(self, user_text: str, ai_response: str, summary: str, context: str):
        """Adiciona uma nova mensagem  memria"""
        timestamp = datetime.datetime.now().isoformat()
        message_id = str(datetime.datetime.now().timestamp())

        new_message = Message(
            id=message_id,
            timestamp=timestamp,
            user_text=user_text,
            ai_response=ai_response,
            summary=summary,
            context=context
        )

        # Adicionar s mensagens recentes (mximo 10)
        self.session.recent_messages.append(new_message)
        if len(self.session.recent_messages) > MAX_RECENT_MESSAGES:
            self.session.recent_messages.pop(0)

        # Adicionar ao histrico completo
        self.session.full_history.append(new_message)

        # Salvar memria
        self._save_memory()

    def get_recent_messages(self) -> List[Message]:
        """Retorna as ltimas mensagens"""
        return self.session.recent_messages

    def get_full_history(self) -> List[Message]:
        """Retorna o histrico completo"""
        return self.session.full_history

    def get_context_summary(self) -> str:
        """Gera um resumo do contexto atual"""
        if not self.session.recent_messages:
            return "Nenhuma conversa recente."

        summaries = [msg.summary for msg in self.session.recent_messages]
        return " | ".join(summaries)

    def clear_memory(self):
        """Limpa toda a memria"""
        self.session = MemorySession(recent_messages=[], full_history=[])
        self._save_memory()

    def search_history(self, query: str) -> List[Message]:
        """Busca no histrico por uma query"""
        query_lower = query.lower()
        return [
            msg for msg in self.session.full_history
            if query_lower in msg.user_text.lower() or query_lower in msg.ai_response.lower()
        ]

# Funo de convenincia para uso no sts_orchestrator
def get_memory_system() -> MemorySystem:
    """Retorna uma instncia do MemorySystem"""
    return MemorySystem()