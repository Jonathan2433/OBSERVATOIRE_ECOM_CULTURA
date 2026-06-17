"""Code partagé entre l'API et le worker (base de données + modèles ORM).

Garantit un schéma unique sans duplication : les deux services importent
``common.db`` et ``common.models``.
"""
