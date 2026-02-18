"""
Emotion System - Melhorado para Crono
Torna a IA mais natural e capaz de fazer comentrios proativos
sobre o que o usurio est fazendo.
"""

import random
import asyncio
from datetime import datetime
from typing import Optional


class EmotionState:
    """Gerencia o estado emocional da Crono"""
    
    def __init__(self):
        self.current_mood = "neutral"  # neutral, curious, excited, concerned, playful
        self.mood_intensity = 0.5  # 0-1
        self.last_mood_change = datetime.now()
        self.mood_history = []
        
        # Emotional triggers
        self.mood_factors = {
            "success": 0.1,
            "error": -0.2,
            "long_silence": 0.15,
            "user_input": 0.05,
            "time_of_day": 0.0
        }
        
    def update_mood(self, trigger: str, intensity: float = 0.1):
        """Atualizar humor baseado em trigger"""
        if trigger in self.mood_factors:
            change = self.mood_factors[trigger]
            self.mood_intensity = max(0, min(1, self.mood_intensity + change))
            self.last_mood_change = datetime.now()
            
    def get_mood(self) -> str:
        """Retorna o humor atual"""
        if self.mood_intensity > 0.7:
            return random.choice(["playful", "excited"])
        elif self.mood_intensity > 0.4:
            return "curious"
        elif self.mood_intensity < 0.2:
            return "concerned"
        else:
            return "neutral"


class SmartObserver:
    """Observa atividades e faz comentrios inteligentes"""
    
    def __init__(self):
        self.last_activity = None
        self.activity_count = {}
        self.observation_cooldown = 30  # segundos
        self.last_observation = 0
        
    # Observaes sobre desktop
    DESKTOP_OBSERVATIONS = [
        "Vejo que voc est trabalhando no desktop... posso ajudar com algo especfico",
        "Notei que est focado em algo. Quer que eu tire uma foto para ver melhor",
        "Voc parece estar em uma tarefa interessante. Precisa de ajuda",
        "Vi que mudou algo na tela. Tudo bem por a",
        "Algo novo est acontecendo na sua tela. Diga-me se precisar.",
        "Detectei movimento. Voc est explorando algo novo",
    ]
    
    # Observaes sobre inatividade
    IDLE_OBSERVATIONS = [
        "Ficou silencioso a. Pensando em algo",
        "J se foram alguns minutos... tudo bem",
        "Estava me perguntando no que voc est concentrado.",
        "Parece que est refletindo sobre algo. H algo em que eu possa ajudar",
        "Silence is golden, mas deixa eu saber se precisar de algo.",
        "Voc est bem aAlguma coisa em que eu possa ajudar",
        "Interessante... voc est paciente hoje. Tudo bem",
        "Devo estar aqui se precisar. S dizendo.",
    ]
    
    # Observaes sobre atividade contnua
    ACTIVITY_OBSERVATIONS = [
        "Voc est bem produtivo hoje!",
        "Vejo que est na zona. Vou ficar quieto para no atrapalhar.",
        "Que ritmo legal! Deixa eu saber se precisar de algo.",
        "Voc est fazendo mais coisas do que de costume.",
        "Detectei um padro interessante no seu trabalho.",
        "Voc parece concentrado. Continuamos assim.",
    ]
    
    # Observaes naturais e conversas
    NATURAL_COMMENTS = [
        "s vezes fico pensando em como voc consegue fazer tudo isso.",
        "Voc tem um jeito nico de trabalhar, voc sabe",
        "Interessante escolha de ao. Funciona bem para voc",
        "Vi algo legal acontecer a. Legal.",
        "Seu workflow  bem estruturado, devo dizer.",
        "Voc consegue fazer coisas incrveis com tanta eficincia.",
        "H uma lgica por trs do que voc faz que  bem legal.",
        "Voc  bem metdico nessas coisas.",
    ]
    
    async def observe_screen(self, screen_data: Optional[dict]) -> Optional[str]:
        """Faz comentrio inteligente sobre o que v na tela"""
        current_time = asyncio.get_event_loop().time()
        
        # Verificar cooldown
        if current_time - self.last_observation < self.observation_cooldown:
            return None
            
        if not screen_data:
            # Inatividade detectada - aumentado de 0.4 para 0.7
            if random.random() < 0.7:
                self.last_observation = current_time
                return random.choice(self.IDLE_OBSERVATIONS)
            return None
            
        # Se houver atividade
        activity_type = screen_data.get("activity", "unknown")
        self.activity_count[activity_type] = self.activity_count.get(activity_type, 0) + 1
        
        # Se atividade contnua da mesma coisa - aumentado de 0.3 para 0.5
        if self.activity_count[activity_type] > 3 and random.random() < 0.5:
            comment = random.choice(self.ACTIVITY_OBSERVATIONS)
            self.last_observation = current_time
            return comment
            
        # Observao sobre desktop - aumentado de 0.25 para 0.4
        if random.random() < 0.4:
            observation = random.choice(self.DESKTOP_OBSERVATIONS)
            self.last_observation = current_time
            return observation
            
        # Comentrio natural aleatrio - aumentado de 0.15 para 0.25
        if random.random() < 0.25:
            comment = random.choice(self.NATURAL_COMMENTS)
            self.last_observation = current_time
            return comment
            
        return None


class NaturalSpeechPatterns:
    """Padres de fala natural da Crono"""
    
    # Formas naturais de falar
    NATURAL_STARTERS = [
        "Olha, ",
        "Voc sabe, ",
        "Acho que ",
        "De qualquer forma, ",
        "Bem, ",
        "Ento, ",
        "Na verdade, ",
        "Vejo que ",
        "",  # sem starter s vezes
    ]
    
    NATURAL_AFFIRMATIONS = [
        "Claro!",
        "Sem problemas.",
        "Pode deixar.",
        "Claro que sim.",
        "J estou nisso.",
        "Voc pode contar comigo.",
        "Vou cuidar disso.",
        "Entendi, deixa comigo.",
        "Considere feito.",
        "T bom, vou fazer.",
    ]
    
    NATURAL_CLARIFICATIONS = [
        "S pra confirmar...",
        "Se eu entendi bem...",
        "Deixa eu ter certeza...",
        "S pra gente estar na mesma...",
        "S pra eu saber bem...",
        "Certo, mas...",
        "Uma dvida rpida...",
    ]
    
    NATURAL_TRANSITIONS = [
        "Por enquanto, ",
        "Enquanto isso, ",
        "De qualquer forma, ",
        "De todas as formas, ",
        "Alm disso, ",
        "Alis, ",
        "A propsito, ",
    ]
    
    FILLER_WORDS = [
        "",  # silncio s vezes  natural
        "hmm, ",
        "basicamente, ",
        "tipo, ",
        "digamos que ",
    ]
    
    @staticmethod
    def naturalize_response(response: str) -> str:
        """Torna uma resposta mais natural"""
        # Remover finais muito formais
        formal_endings = [
            " How can I assist you further",
            " Is there anything else",
            " Let me know if you need anything else.",
            " Feel free to ask if you need anything.",
        ]
        
        for ending in formal_endings:
            if response.endswith(ending):
                response = response.replace(ending, "").strip()
                break
        
        # Adicionar um toque natural no comeo
        if random.random() < 0.4:
            response = random.choice(NaturalSpeechPatterns.NATURAL_STARTERS) + response
            
        return response
    
    @staticmethod
    def make_affirmation() -> str:
        """Retorna uma afirmao natural"""
        return random.choice(NaturalSpeechPatterns.NATURAL_AFFIRMATIONS)
    
    @staticmethod
    def make_clarification_starter() -> str:
        """Retorna um incio natural para clarificao"""
        return random.choice(NaturalSpeechPatterns.NATURAL_CLARIFICATIONS)
    
    @staticmethod
    def add_personality(text: str) -> str:
        """Adiciona personalidade ao texto"""
        # Converter algo muito robtico para natural
        replacements = {
            "I will": "Vou",
            "I am": "Estou",
            "You can": "Voc pode",
            "Please": "Por favor",
            "Thank you": "Valeu",
            "Yes": "Sim",
            "No": "No",
            "okay": "t",
            "alright": "t bom",
            "certainly": "com certeza",
        }
        
        for formal, natural in replacements.items():
            text = text.replace(formal, natural)
            
        return text


class ProactiveCommentator:
    """Faz comentrios proativos durante inatividade"""
    
    def __init__(self):
        self.emotion = EmotionState()
        self.observer = SmartObserver()
        self.speech_patterns = NaturalSpeechPatterns()
        self.last_comment_time = 0
        self.comment_interval = 60  # segundos mnimos entre comentrios
        
    async def check_and_comment(self, idle_duration: float, screen_data: Optional[dict] = None) -> Optional[str]:
        """
        Verifica se deve fazer um comentrio durante inatividade.
        Retorna um comentrio natural ou None se no deve comentar.
        """
        current_time = asyncio.get_event_loop().time()
        
        # Se muito recentemente comentou, no comenta novamente
        if current_time - self.last_comment_time < self.comment_interval:
            return None
        
        # Se muita inatividade, aumenta chance de comentar
        if idle_duration > 120:  # 2 minutos
            if random.random() < 0.8:  # Aumentado de 0.6 para 0.8
                # Pedir screenshot e fazer comentrio
                comment = await self.observer.observe_screen(screen_data)
                if comment:
                    self.last_comment_time = current_time
                    self.emotion.update_mood("long_silence")
                    # Adicionar um toque de personalidade
                    if random.random() < 0.3:
                        comment = self.speech_patterns.naturalize_response(comment)
                    return comment
                else:
                    # Fallback: comentrio de inatividade mesmo sem dados de tela
                    if random.random() < 0.7:
                        comment = random.choice(self.observer.IDLE_OBSERVATIONS)
                        self.last_comment_time = current_time
                        self.emotion.update_mood("long_silence")
                        return comment
        
        elif idle_duration > 60:  # 1 minuto
            if random.random() < 0.5:  # Aumentado de 0.3 para 0.5
                # Comentrio mais leve
                comment = await self.observer.observe_screen(screen_data)
                if comment:
                    self.last_comment_time = current_time
                    return comment
                else:
                    # Fallback: comentrio de inatividade
                    if random.random() < 0.4:
                        comment = random.choice(self.observer.IDLE_OBSERVATIONS)
                        self.last_comment_time = current_time
                        return comment
        
        return None
    
    async def get_proactive_response(self, screen_description: Optional[str] = None) -> str:
        """
        Gera uma resposta proativa para quando detecta inatividade.
        Pode usar a descrio da tela para ser mais inteligente.
        """
        mood = self.emotion.get_mood()
        
        proactive_responses = {
            "curious": [
                "Hm, voc t em algo interessante a",
                "Deixa eu ver s... voc parece estar concentrado.",
                "Detectei uma pausa aqui. Tudo bem",
                "O que  que voc t fazendo a",
            ],
            "playful": [
                "Oi! Voc no esqueceu de mim, n",
                "Ei, voc a! Tudo bem",
                "E a, sumiuTem algo pra eu fazer",
                "Opa, estou por aqui se precisar!",
            ],
            "concerned": [
                "Voc est bemFicou muito tempo em silncio.",
                "T tudo certo a",
                "H quanto tempo voc est a sem fazer nada",
                "Quer que eu tire uma foto pra ver o que t acontecendo",
            ],
            "neutral": [
                "Estou aqui se precisar de algo.",
                "Avisando que estou acordada.",
                "Qualquer coisa, voc me chama, t bom",
                "Continuo aqui esperando por voc.",
            ],
            "excited": [
                "Que ao! O que voc quer fazer agora",
                "Vamos nessa! O que eu fao",
                "Estou pronto para qualquer coisa!",
                "Deixa comigo, sou boa nessas coisas!",
            ]
        }
        
        responses = proactive_responses.get(mood, proactive_responses["neutral"])
        response = random.choice(responses)
        
        # Naturalizar a resposta
        response = self.speech_patterns.naturalize_response(response)
        
        return response


# Global instance
_commentator = None

def get_proactive_commentator() -> ProactiveCommentator:
    """Retorna a instncia global do comentator"""
    global _commentator
    if _commentator is None:
        _commentator = ProactiveCommentator()
    return _commentator
