"""Bigfish 新架构的结构化投资知识层。"""

from investment_os.knowledge.database import create_knowledge_repository, create_knowledge_service
from investment_os.knowledge.models import KnowledgeBase
from investment_os.knowledge.repository import KnowledgeRepository
from investment_os.knowledge.service import KnowledgeService

__all__ = [
    "KnowledgeBase",
    "KnowledgeRepository",
    "KnowledgeService",
    "create_knowledge_repository",
    "create_knowledge_service",
]
