"""Мелкие общие утилиты."""
import random
import sys


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def backoff(attempts: int) -> float:
    """Экспоненциальная задержка с джиттером"""
    return min(0.3 * (2 ** min(attempts, 4)), 3.0) * (0.5 + random.random())
