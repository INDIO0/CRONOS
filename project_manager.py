import os
import json
from tts import edge_speak

def project_manager(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None
) -> bool:
    """
    Gerencia o ciclo de vida do projeto com estrutura e feedback aprimorados.
    """
    if session_memory is None:
        return False

    action = parameters.get("action") # 'start', 'exit', 'status'
    project_name = parameters.get("project_name")
    project_context = parameters.get("project_context", "Projeto Geral")
    
    # Base directory for projects (relative to project root)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    base_dir = os.path.join(project_root, "PROJETOS")
    os.makedirs(base_dir, exist_ok=True)

    try:
        if action == "start":
            if not project_name:
                msg = "Senhor, preciso do nome do projeto para começar."
                if player: player.write_log(f"Crono: {msg}")
                edge_speak(msg, player)
                return False

            project_path = os.path.join(base_dir, project_name)
            
            # Create project structure
            folders = ["", "src", "docs", "tests", "assets"]
            for folder in folders:
                os.makedirs(os.path.join(project_path, folder), exist_ok=True)
            
            # Create/Update context file
            context_file = os.path.join(project_path, "context.json")
            context_data = {
                "project_name": project_name,
                "description": project_context,
                "status": "active",
                "created_at": str(os.path.getctime(project_path))
            }
            with open(context_file, "w", encoding="utf-8") as f:
                json.dump(context_data, f, indent=4, ensure_ascii=False)
            
            # Create an initial README if it doesn't exist
            readme_path = os.path.join(project_path, "README.md")
            if not os.path.exists(readme_path):
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(f"# {project_name}\n\n{project_context}")

            session_memory.set_active_project(project_name, project_path, project_context)
            
            msg = f"Projeto '{project_name}' inicializado com sucesso, senhor. Criei a estrutura de pastas e o arquivo de contexto."
            if player: player.write_log(f"Crono: {msg}")
            edge_speak(response if response else msg, player)
            return True

        elif action == "exit":
            active = session_memory.get_active_project()
            if active:
                name = active["name"]
                session_memory.clear_active_project()
                msg = f"Encerrando sessão do projeto {name}, senhor. O caminho de trabalho foi resetado."
            else:
                msg = "Não há nenhum projeto ativo no momento, senhor."
            
            if player: player.write_log(f"Crono: {msg}")
            edge_speak(response if response else msg, player)
            return True
            
        elif action == "status":
            active = session_memory.get_active_project()
            if active:
                msg = f"Estamos trabalhando no projeto '{active['name']}'. Localizado em: {active['path']}"
            else:
                msg = "Não temos nenhum projeto ativo no momento, senhor."
            
            if player: player.write_log(f"Crono: {msg}")
            edge_speak(response if response else msg, player)
            return True

    except Exception as e:
        err = f"Erro no gerenciador de projetos: {e}"
        if player: player.write_log(f"Crono: {err}")
        edge_speak("Falha ao gerenciar o projeto, senhor. Verifique as permissões de pasta.", player)
        return False
    
    return False
