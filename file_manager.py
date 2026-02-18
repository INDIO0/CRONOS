"""
Advanced File Manager for Crono
================================
Mdulo avanado de gerenciamento de arquivos com:
- Criao dinmica de diretrios via subprocess
- Monitoramento e inspeo de pastas
- Metadados de arquivos e subpastas
- Validao de caminhos
"""

import os
import subprocess
import shutil
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
import mimetypes


@dataclass
class FileMetadata:
    """Metadados de um arquivo"""
    name: str
    path: str
    size: int
    size_human: str
    type: str
    extension: str
    created: str
    modified: str
    is_file: bool
    is_directory: bool
    is_hidden: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionrio"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Converte para JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class DirectoryScanResult:
    """Resultado do escaneamento de diretrio"""
    path: str
    total_files: int
    total_directories: int
    total_size: int
    total_size_human: str
    files: List[FileMetadata]
    directories: List[FileMetadata]
    scan_time: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionrio"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Converte para JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class PathValidator:
    """Validador de caminhos"""
    
    @staticmethod
    def is_valid_path(path: str) -> bool:
        """Verifica se um caminho  vlido"""
        try:
            Path(path).resolve()
            return True
        except (OSError, RuntimeError):
            return False
    
    @staticmethod
    def is_absolute_path(path: str) -> bool:
        """Verifica se o caminho  absoluto"""
        return os.path.isabs(path)
    
    @staticmethod
    def normalize_path(path: str) -> str:
        """Normaliza um caminho"""
        return str(Path(path).resolve())
    
    @staticmethod
    def expand_user_path(path: str) -> str:
        """Expande caminhos do usurio (~)"""
        return str(Path(path).expanduser())
    
    @staticmethod
    def get_special_path(special: str) -> Optional[str]:
        """Retorna caminhos especiais do sistema"""
        user_home = os.path.expanduser('~')
        onedrive_root = os.environ.get('OneDrive') or os.path.join(user_home, 'OneDrive')
        onedrive_desktop = os.path.join(onedrive_root, 'Desktop')
        desktop_default = os.path.join(user_home, 'Desktop')
        desktop_path = onedrive_desktop if os.path.exists(onedrive_desktop) else desktop_default
        special_paths = {
            'desktop': desktop_path,
            'documents': os.path.join(os.path.expanduser('~'), 'Documents'),
            'downloads': os.path.join(os.path.expanduser('~'), 'Downloads'),
            'pictures': os.path.join(os.path.expanduser('~'), 'Pictures'),
            'music': os.path.join(os.path.expanduser('~'), 'Music'),
            'videos': os.path.join(os.path.expanduser('~'), 'Videos'),
            'home': os.path.expanduser('~'),
            'appdata': os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming'),
            'temp': os.environ.get('TEMP', os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')),
        }
        
        special_lower = special.lower().replace(' ', '').replace('_', '')
        return special_paths.get(special_lower)
    
    @staticmethod
    def validate_and_normalize(path: str) -> Tuple[bool, str, Optional[str]]:
        """
        Valida e normaliza um caminho
        
        Returns:
            (is_valid, normalized_path, error_message)
        """
        # Expandir caminho do usurio
        path = PathValidator.expand_user_path(path)
        
        # Verificar se  um caminho especial
        special_path = PathValidator.get_special_path(path)
        if special_path:
            path = special_path
        
        # Normalizar caminho
        try:
            normalized = PathValidator.normalize_path(path)
        except Exception as e:
            return False, path, f"Erro ao normalizar caminho: {e}"
        
        # Validar caminho
        if not PathValidator.is_valid_path(normalized):
            return False, normalized, "Caminho invlido"
        
        return True, normalized, None


class DirectoryCreator:
    """Criador de diretrios via subprocess"""
    
    @staticmethod
    def create_directory(path: str, name: Optional[str] = None, 
                      use_subprocess: bool = True) -> Tuple[bool, str, Optional[str]]:
        """
        Cria um diretrio
        
        Args:
            path: Caminho base onde criar o diretrio
            name: Nome do diretrio (opcional)
            use_subprocess: Se True, usa subprocess para criar via CMD
        
        Returns:
            (success, full_path, error_message)
        """
        # Validar e normalizar caminho
        is_valid, normalized_path, error = PathValidator.validate_and_normalize(path)
        if not is_valid:
            return False, path, error
        
        # Construir caminho completo
        if name:
            full_path = os.path.join(normalized_path, name)
        else:
            full_path = normalized_path
        
        # Verificar se j existe
        if os.path.exists(full_path):
            return False, full_path, "Diretrio j existe"
        
        try:
            if use_subprocess:
                # Criar via subprocess (CMD)
                result = subprocess.run(
                    ['cmd', '/c', 'mkdir', full_path],
                    capture_output=True,
                    text=True,
                    shell=True
                )
                
                if result.returncode != 0:
                    return False, full_path, f"Erro ao criar diretrio via CMD: {result.stderr}"
            else:
                # Criar via Python
                os.makedirs(full_path, exist_ok=True)
            
            return True, full_path, None
            
        except Exception as e:
            return False, full_path, f"Erro ao criar diretrio: {e}"
    
    @staticmethod
    def create_nested_directories(base_path: str, structure: Dict[str, Any],
                                use_subprocess: bool = True) -> Tuple[bool, List[str], Optional[str]]:
        """
        Cria uma estrutura de diretrios aninhados
        
        Args:
            base_path: Caminho base
            structure: Dicionrio representando a estrutura de diretrios
            use_subprocess: Se True, usa subprocess para criar via CMD
        
        Returns:
            (success, created_paths, error_message)
        """
        is_valid, normalized_path, error = PathValidator.validate_and_normalize(base_path)
        if not is_valid:
            return False, [], error
        
        created_paths = []
        
        def create_structure(current_path: str, struct: Dict[str, Any]):
            """Funo recursiva para criar estrutura"""
            for name, content in struct.items():
                full_path = os.path.join(current_path, name)
                
                # Criar diretrio
                success, path, err = DirectoryCreator.create_directory(
                    full_path, use_subprocess=use_subprocess
                )
                
                if success:
                    created_paths.append(path)
                    
                    # Se houver subdiretrios, criar recursivamente
                    if isinstance(content, dict):
                        create_structure(path, content)
        
        try:
            create_structure(normalized_path, structure)
            return True, created_paths, None
        except Exception as e:
            return False, created_paths, f"Erro ao criar estrutura: {e}"


class FileInspector:
    """Inspetor de arquivos e diretrios"""
    
    @staticmethod
    def get_file_metadata(file_path: str) -> Optional[FileMetadata]:
        """
        Obtm metadados de um arquivo ou diretrio
        
        Args:
            file_path: Caminho do arquivo/diretrio
        
        Returns:
            FileMetadata ou None se erro
        """
        try:
            path = Path(file_path)
            stat = path.stat()
            
            # Determinar tipo
            mime_type, _ = mimetypes.guess_type(str(path))
            file_type = mime_type or "unknown"
            
            # Verificar se est oculto
            is_hidden = path.name.startswith('.') or (
                hasattr(os, 'stat') and 
                (os.stat(file_path).st_file_attributes & 2) if hasattr(os.stat(file_path), 'st_file_attributes') else False
            )
            
            # Formatar tamanho
            size = stat.st_size
            size_human = FileInspector._format_size(size)
            
            # Formatar datas
            created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            return FileMetadata(
                name=path.name,
                path=str(path.resolve()),
                size=size,
                size_human=size_human,
                type=file_type,
                extension=path.suffix.lower() if path.suffix else "",
                created=created,
                modified=modified,
                is_file=path.is_file(),
                is_directory=path.is_dir(),
                is_hidden=is_hidden
            )
            
        except Exception as e:
            print(f"Erro ao obter metadados de {file_path}: {e}")
            return None
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Formata tamanho em bytes para formato legvel"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    @staticmethod
    def scan_directory(path: str, recursive: bool = False, 
                     include_hidden: bool = False) -> Optional[DirectoryScanResult]:
        """
        Escaneia um diretrio e retorna informaes detalhadas
        
        Args:
            path: Caminho do diretrio
            recursive: Se True, escaneia recursivamente
            include_hidden: Se True, inclui arquivos ocultos
        
        Returns:
            DirectoryScanResult ou None se erro
        """
        try:
            is_valid, normalized_path, error = PathValidator.validate_and_normalize(path)
            if not is_valid:
                print(f"Erro: {error}")
                return None
            
            if not os.path.exists(normalized_path):
                print(f"Erro: Diretrio no existe: {normalized_path}")
                return None
            
            files = []
            directories = []
            total_size = 0
            
            def scan(current_path: str):
                """Funo recursiva para escanear"""
                nonlocal total_size
                
                try:
                    for item in os.listdir(current_path):
                        item_path = os.path.join(current_path, item)
                        
                        # Pular arquivos ocultos se no solicitado
                        if not include_hidden and item.startswith('.'):
                            continue
                        
                        metadata = FileInspector.get_file_metadata(item_path)
                        if metadata:
                            total_size += metadata.size
                            
                            if metadata.is_directory:
                                directories.append(metadata)
                                if recursive:
                                    scan(item_path)
                            else:
                                files.append(metadata)
                        else:
                            files.append(FileMetadata(
                                name=item,
                                path=item_path,
                                size=0,
                                size_human="0 B",
                                type="unknown",
                                extension="",
                                created="",
                                modified="",
                                is_file=True,
                                is_directory=False,
                                is_hidden=item.startswith('.')
                            ))
                
                except PermissionError:
                    print(f"Aviso: Permisso negada para {current_path}")
                except Exception as e:
                    print(f"Erro ao escanear {current_path}: {e}")
            
            scan(normalized_path)
            
            scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            return DirectoryScanResult(
                path=normalized_path,
                total_files=len(files),
                total_directories=len(directories),
                total_size=total_size,
                total_size_human=FileInspector._format_size(total_size),
                files=files,
                directories=directories,
                scan_time=scan_time
            )
            
        except Exception as e:
            print(f"Erro ao escanear diretrio: {e}")
            return None
    
    @staticmethod
    def list_directory(path: str, detailed: bool = True) -> Optional[List[FileMetadata]]:
        """
        Lista o contedo de um diretrio
        
        Args:
            path: Caminho do diretrio
            detailed: Se True, inclui metadados completos
        
        Returns:
            Lista de FileMetadata ou None se erro
        """
        try:
            is_valid, normalized_path, error = PathValidator.validate_and_normalize(path)
            if not is_valid:
                print(f"Erro: {error}")
                return None
            
            if not os.path.exists(normalized_path):
                print(f"Erro: Diretrio no existe: {normalized_path}")
                return None
            
            items = []
            
            for item in os.listdir(normalized_path):
                item_path = os.path.join(normalized_path, item)
                
                if detailed:
                    metadata = FileInspector.get_file_metadata(item_path)
                    if metadata:
                        items.append(metadata)
                else:
                    items.append(FileMetadata(
                        name=item,
                        path=item_path,
                        size=0,
                        size_human="",
                        type="",
                        extension="",
                        created="",
                        modified="",
                        is_file=os.path.isfile(item_path),
                        is_directory=os.path.isdir(item_path),
                        is_hidden=item.startswith('.')
                    ))
            
            # Ordenar: diretrios primeiro, depois arquivos
            items.sort(key=lambda x: (not x.is_directory, x.name.lower()))
            
            return items
            
        except Exception as e:
            print(f"Erro ao listar diretrio: {e}")
            return None


class FileManager:
    """Gerenciador de arquivos principal"""
    
    def __init__(self):
        self.validator = PathValidator()
        self.creator = DirectoryCreator()
        self.inspector = FileInspector()
    
    def create_directory(self, path: str, name: Optional[str] = None,
                       use_subprocess: bool = True) -> Dict[str, Any]:
        """
        Cria um diretrio
        
        Returns:
            Dicionrio com resultado da operao
        """
        success, full_path, error = self.creator.create_directory(path, name, use_subprocess)
        
        return {
            'success': success,
            'path': full_path,
            'error': error,
            'operation': 'create_directory'
        }
    
    def create_structure(self, base_path: str, structure: Dict[str, Any],
                        use_subprocess: bool = True) -> Dict[str, Any]:
        """
        Cria uma estrutura de diretrios
        
        Returns:
            Dicionrio com resultado da operao
        """
        success, created_paths, error = self.creator.create_nested_directories(
            base_path, structure, use_subprocess
        )
        
        return {
            'success': success,
            'created_paths': created_paths,
            'error': error,
            'operation': 'create_structure'
        }
    
    def scan_directory(self, path: str, recursive: bool = False,
                      include_hidden: bool = False) -> Dict[str, Any]:
        """
        Escaneia um diretrio
        
        Returns:
            Dicionrio com resultado da operao
        """
        result = self.inspector.scan_directory(path, recursive, include_hidden)
        
        if result:
            return {
                'success': True,
                'result': result.to_dict(),
                'error': None,
                'operation': 'scan_directory'
            }
        else:
            return {
                'success': False,
                'result': None,
                'error': 'Erro ao escanear diretrio',
                'operation': 'scan_directory'
            }
    
    def list_directory(self, path: str, detailed: bool = True) -> Dict[str, Any]:
        """
        Lista o contedo de um diretrio
        
        Returns:
            Dicionrio com resultado da operao
        """
        items = self.inspector.list_directory(path, detailed)
        
        if items is not None:
            return {
                'success': True,
                'items': [item.to_dict() for item in items],
                'count': len(items),
                'error': None,
                'operation': 'list_directory'
            }
        else:
            return {
                'success': False,
                'items': [],
                'count': 0,
                'error': 'Erro ao listar diretrio',
                'operation': 'list_directory'
            }
    
    def get_file_info(self, path: str) -> Dict[str, Any]:
        """
        Obtm informaes de um arquivo
        
        Returns:
            Dicionrio com resultado da operao
        """
        metadata = self.inspector.get_file_metadata(path)
        
        if metadata:
            return {
                'success': True,
                'metadata': metadata.to_dict(),
                'error': None,
                'operation': 'get_file_info'
            }
        else:
            return {
                'success': False,
                'metadata': None,
                'error': 'Erro ao obter informaes do arquivo',
                'operation': 'get_file_info'
            }
    
    def validate_path(self, path: str) -> Dict[str, Any]:
        """
        Valida um caminho
        
        Returns:
            Dicionrio com resultado da operao
        """
        is_valid, normalized_path, error = self.validator.validate_and_normalize(path)
        
        return {
            'success': is_valid,
            'path': normalized_path,
            'error': error,
            'operation': 'validate_path'
        }


# Funo de convenincia para uso no sts_orchestrator
def get_file_manager() -> FileManager:
    """Retorna uma instncia do FileManager"""
    return FileManager()
