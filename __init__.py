"""AEGIS — Autonomous Environment Guardian & Integration System.

Three-layer integration framework unifying:
  L1: Claude Guardian  — system daemon, session state machine, health monitoring
  L2: Memory Forest     — structured memory, heartbeat, GC, task tracking
  L3: RAG Knowledge Base — vector search, RAG generation, knowledge expansion

AEGIS bridges these layers so they function as a coherent autonomous substrate:
  - Guardian session events → Forest heartbeat updates → KB context indexing
  - Guardian health alerts → Forest alert nodes → KB solution search
  - KB knowledge gaps → Forest task creation → Guardian background resolution
"""
__version__ = "1.0.0"
