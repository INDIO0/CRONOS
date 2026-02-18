# CRONOS - Documentacao do Projeto

**Visao Geral**
Cronos e um assistente de voz full-duplex com orquestracao de acoes no Windows. Ele escuta e fala ao mesmo tempo, permite interrupcao (barge-in), executa tarefas locais (abrir apps, digitar, controlar tela, timers) e consulta modelos da Groq para STT e LLM. O sistema tem UI propria, monitora o estado do microfone, aplica VAD adaptativo e tem mecanismos de memoria persistente.

**Fluxo Principal (STS Full-Duplex)**
1. `main.py` inicia a UI, configura monitor, carrega o LLM e sobe o `CronoSTSOrchestrator`.
2. `sts_engine.py` fica ouvindo continuamente o microfone (VAD + cancelamento de eco).
3. Quando detecta fala, grava o buffer e envia ao STT da Groq (Whisper v3).
4. O texto transcrito e filtrado (eco/ruido) e passa por correcoes de vocabulario.
5. `llm.py` gera um plano estruturado (ou resposta simples).
6. O orquestrador executa acoes (se houver) e fala a resposta via TTS.

**Arquitetura (componentes principais)**
- `main.py`
  Entry point do modo full-duplex. Inicializa UI, monitor manager e orchestrator.

- `sts_engine.py`
  Motor STS: VAD, buffer de audio, barge-in, cancelamento de eco e STT Groq.
  Usa `GROQ_STT_MODEL=whisper-large-v3` por padrao.

- `sts_orchestrator.py`
  Orquestra o pipeline: comandos especiais, memoria, LLM, acoes e TTS.
  Faz controle de standby/snooze, modo digitacao, e manutencao de estado.

- `llm.py`
  Camada LLM com prompt estruturado e retorno em JSON.
  Faz fallback local para perguntas de tempo/timers.

- `streaming_tts.py` e `tts.py`
  TTS com streaming (edge-tts) e suporte a interrupcao.

- `ui.py`
  Interface do Cronos, logs e controle de estado.

**STT (Speech-to-Text) com Groq**
- Implementacao full-duplex em `sts_engine.py`.
- Implementacao discreta em `speech_to_text.py` (uso auxiliar/testes).
- Configuracoes via `.env`:
  `GROQ_API_KEY`, `GROQ_STT_MODEL`, `GROQ_STT_LANGUAGE`, `GROQ_STT_TEMPERATURE`.

**TTS (Text-to-Speech)**
- `streaming_tts.py` usa edge-tts para baixa latencia.
- `tts.py` integra com o STS Engine para evitar loop de eco.

**LLM e Planejamento**
- `llm.py` construi prompts com memoria e retorna plano normalizado.
- Usa `core/prompt.json` e `core/prompt.txt`.
- Modelo padrao: `gpt-oss-120b` via Groq (`GROQ_LLM_MODEL`).

**Memoria (o que e salvo)**
- Persistente em JSON:
  `core/memory_store.py` salva perfil, notas e mensagens em `memory.json`.
  `core/mem0_lite.py` salva memorias curtas/resumos em `mem0.json`.
- O orquestrador atualiza perfil com `memory_update` do LLM.
- O sistema guarda notas quando voce pede para lembrar algo.

**Visao (Vision)**
- `actions/screen_vision.py` captura a tela e envia para modelos visuais.
- Usa Groq Vision.
- `vision/vision_system.py` adiciona cache e metricas.

**Acoes Disponiveis**
Arquivos em `actions/`:
- `open_app.py` e `close_app.py`: abre/fecha apps.
- `open_website.py`: abre sites.
- `type_text.py`: digita texto.
- `keyboard_control.py`: teclas rapidas.
- `screen_control.py`: controle de tela.
- `visual_navigator.py`: procura e interage com alvos visuais.
- `weather_report.py`: clima (depende de integracao).
- `file_operations.py`: operacoes de arquivos.
- `project_manager.py`: contexto de projetos.
- `timer.py`: temporizadores.
- `calendar.py`: agendamentos.
- `media_player.py`: tocar playlists.
- `send_message.py`: envio de mensagens.
- `ada_web_agent.py`: Web Agent extraido do A.D.A e incorporado localmente para busca web e leitura de URLs.

**Vocabulario Personalizado**
- `user_vocabulary.py` permite corrigir palavras ou mapear variantes.
- Comandos do tipo "quando eu falar X, entenda Y".

**Monitoramento e Utilitarios**
- `system_monitor.py`: CPU, RAM e processos.
- `monitor_manager.py`: multi-monitor / mover janelas.
- `text_selector.py`: leitura e acoes sobre texto selecionado.
- `emotion_system.py`: comentarios proativos.

**Entradas de Execucao**
- Modo recomendado: `main.py` (full-duplex com UI).
- Modulo simples: `orchestrator.py` (legado).
- STT standalone: `speech_to_text.py`.
- STS wrapper: `sts/sts_system.py`.

**Configuracao (.env)**
- `GROQ_API_KEY` (obrigatorio)
- `GROQ_LLM_MODEL` (padrao: `gpt-oss-120b`)
- `GROQ_STT_MODEL` (padrao: `whisper-large-v3`)
- `GROQ_STT_LANGUAGE` (padrao: `pt`)
- `GROQ_STT_TEMPERATURE` (padrao: `0`)
- `GROQ_VISION_MODEL` (padrao: `meta-llama/llama-4-maverick-17b-128e-instruct`)
- `OPENROUTER_API_KEY` (opcional, fallback para LLM)

**Integracao A.D.A (somente Web Agent)**
- Cronos incorpora localmente o Web Agent extraido do A.D.A em `actions/ada_web_agent.py`, sem Gemini.
- Intents suportadas: `search_web` e `fetch_web_content`.
- Busca web prioriza SerpAPI quando `SERPAPI_API_KEY` (ou `SERP_API_KEY`) estiver configurada; sem chave, usa fallback DuckDuckGo.
- CAD, impressora e Kasa NAO sao usados nessa integracao.
- A resposta da busca/leitura usa o mesmo LLM do Cronos (Groq/OpenRouter).

**PTT Configuravel**
- O PTT pode ser ligado/desligado no botao `PTT`.
- A tecla de PTT pode ser alterada no campo `Tecla PTT` da barra superior.
- Variavel opcional em `.env`: `CRONO_PTT_KEY` (padrao: `insert`).

**Resumo do que o Cronos faz hoje**
- Assistente de voz full-duplex com STT/TTS em tempo real.
- Executa acoes locais no Windows.
- Analisa a tela com modelos de visao.
- Usa LLM para planejar e responder.
- Mantem memoria persistente em JSON.
- Permite alternar `PTT` pela UI e alterar a tecla de PTT em tempo real.

**Como estender**
- Adicione novas acoes em `actions/` e registre no `sts_orchestrator.py`.
- Ajuste prompt e politicas em `core/prompt.json` e `core/risk_policy.py`.
- Ajuste VAD/limiares com variaveis `CRONO_*` (ver `sts_engine.py`).
