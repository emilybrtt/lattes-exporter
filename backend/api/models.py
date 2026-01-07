from typing import Optional, Dict, Union
from dataclasses import dataclass

@dataclass
class Docente:
    """ Representa o docente e as informações relevantes extraídas do CSV. """
    nome: str
    email: Optional[str] = None
    nacionalidade: Optional[str] = None
    carreira: str
    area_atuacao: str
    admissao: Optional[str] = None
    unidade_academica: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Optional[Dict[str, Union[str, float]]]]:
        """Converte os atributos em um dicionário pronto para serialização JSON."""
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }
    