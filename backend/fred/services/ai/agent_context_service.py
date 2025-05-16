import logging
import httpx
from typing import List, Dict, Optional
import os

# Configuration du logger
logger = logging.getLogger(__name__)

class AgentContextService:
    """
    Service centralisé pour récupérer les contextes des agents auprès de l'API de contexte.
    """
    
    def __init__(self):
        """
        Initialiser le service de contexte avec l'URL de l'API.
        """
        self.context_api_url = os.getenv("CONTEXT_API_URL", "http://localhost:8111")
        # Ajout du préfixe /knowledge/v1 si nécessaire
        if not self.context_api_url.endswith("/knowledge/v1"):
            if not self.context_api_url.endswith("/"):
                self.context_api_url = f"{self.context_api_url}/knowledge/v1"
            else:
                self.context_api_url = f"{self.context_api_url}knowledge/v1"
        
        logger.info(f"Service de contexte initialisé avec l'URL: {self.context_api_url}")
        
        # Cache des contextes par agent
        self.context_cache = {}
    
    async def get_agent_contexts(self, agent_name: str, force_refresh: bool = False) -> List[Dict]:
        """
        Récupère les contextes pour un agent depuis l'API.
        
        Args:
            agent_name (str): Nom de l'agent
            force_refresh (bool): Force le rafraîchissement du cache
            
        Returns:
            List[Dict]: Liste des contextes (dictionnaires avec id, title, content)
        """
        # Si le cache existe et qu'on ne force pas le rafraîchissement, le renvoyer
        if not force_refresh and agent_name in self.context_cache:
            logger.debug(f"Utilisation du cache pour les contextes de l'agent {agent_name}")
            return self.context_cache[agent_name]
        
        try:
            # Construire l'URL correcte
            url = f"{self.context_api_url}/contexts/{agent_name}"
            logger.info(f"Récupération des contextes depuis: {url}")
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                # Mettre à jour le cache
                contexts = response.json()
                self.context_cache[agent_name] = contexts
                
                logger.info(f"Récupération de {len(contexts)} contextes pour l'agent {agent_name}")
                return contexts
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des contextes pour {agent_name}: {str(e)}")
            # Si une erreur se produit lors du rafraîchissement, renvoyer le cache s'il existe
            if agent_name in self.context_cache:
                logger.warning(f"Utilisation du cache existant pour {agent_name} après échec du rafraîchissement")
                return self.context_cache[agent_name]
            return []
            
    def format_contexts_for_prompt(self, contexts: List[Dict]) -> str:
        """
        Formate les contextes pour inclusion dans un prompt d'agent.
        
        Args:
            contexts (List[Dict]): Liste des contextes
            
        Returns:
            str: Texte formaté à ajouter au prompt
        """
        if not contexts:
            return ""
            
        formatted_text = "USE THE FOLLOWING CONTEXT INFORMATION IN YOUR RESPONSES:\n\n"
        for ctx in contexts:
            formatted_text += f"CONTEXT: {ctx['title']}\n{ctx['content']}\n\n"
        logger.info(f"FORMATTED CONTEXT: {formatted_text!r}")  
        return formatted_text
    
    async def get_formatted_contexts(self, agent_name: str, force_refresh: bool = False) -> str:
        """
        Récupère et formate les contextes pour un agent, prêts à être intégrés dans un prompt.
        
        Args:
            agent_name (str): Nom de l'agent
            force_refresh (bool): Force le rafraîchissement du cache
            
        Returns:
            str: Texte formaté des contextes à ajouter au prompt
        """
        contexts = await self.get_agent_contexts(agent_name, force_refresh)
        return self.format_contexts_for_prompt(contexts)
    
    def clear_cache(self, agent_name: Optional[str] = None):
        """
        Efface le cache des contextes.
        
        Args:
            agent_name (str, optional): Nom de l'agent dont il faut effacer le cache.
                                       Si None, efface tout le cache.
        """
        if agent_name:
            if agent_name in self.context_cache:
                del self.context_cache[agent_name]
                logger.info(f"Cache effacé pour l'agent {agent_name}")
        else:
            self.context_cache = {}
            logger.info("Cache de contexte entièrement effacé")