"""
Фильтрация объявлений по ключевым словам и площади.
Конфиг читается из keywords_config.json — можно менять без перезапуска.
"""
import json
from functools import lru_cache
from typing import Optional
from loguru import logger

import config


@lru_cache(maxsize=1)
def _load_config() -> dict:
    with open(config.KEYWORDS_CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def reload_config() -> None:
    """Сбрасывает кэш — вызови если изменил keywords_config.json на лету."""
    _load_config.cache_clear()


def _get_enabled_include_keywords() -> list[str]:
    """Собирает include-слова из всех включённых направлений."""
    cfg = _load_config()
    keywords = []
    for direction_key, direction in cfg.get("directions", {}).items():
        if direction.get("enabled", False):
            keywords.extend(direction.get("include_keywords", []))
    return [kw.lower() for kw in keywords]


def _get_exclude_keywords() -> list[str]:
    cfg = _load_config()
    return [kw.lower() for kw in cfg.get("exclude_keywords", [])]


def _get_area_config() -> dict:
    cfg = _load_config()
    return cfg.get("area_filters", {"min_area": 800, "priority_area": 1000})


# ─── Публичные функции ────────────────────────────────────────────────────────

def matches_include(title: str, description: str = "") -> bool:
    """True если текст содержит хотя бы одно включающее слово из активных направлений."""
    text = (title + " " + description).lower()
    return any(kw in text for kw in _get_enabled_include_keywords())


def matches_exclude(title: str, description: str = "") -> bool:
    """True если текст содержит хоть одно исключающее слово."""
    text = (title + " " + description).lower()
    return any(kw in text for kw in _get_exclude_keywords())


def get_area_flags(area_m2: Optional[float]) -> tuple[str, bool, bool]:
    """
    Возвращает (verdict, priority_flag, area_unknown_flag).
    verdict: 'include_priority' | 'include_standard' | 'include_unknown' | 'exclude'
    """
    area_cfg = _get_area_config()
    min_area = area_cfg.get("min_area", 800)
    priority_area = area_cfg.get("priority_area", 1000)

    if area_m2 is None:
        return "include_unknown", False, True
    if area_m2 >= priority_area:
        return "include_priority", True, False
    if area_m2 >= min_area:
        return "include_standard", False, False
    return "exclude", False, False


def should_include(title: str, description: str = "", area_m2: Optional[float] = None) -> tuple[bool, bool, bool]:
    """
    Главная функция фильтрации.

    Returns:
        (include, priority_flag, area_unknown_flag)
        include=False → объявление не добавляем в БД
    """
    # 1. Должно содержать хотя бы одно include-слово
    if not matches_include(title, description):
        return False, False, False

    # 2. Не должно содержать exclude-слова
    if matches_exclude(title, description):
        logger.debug("Исключено по стоп-словам: {}", title[:60])
        return False, False, False

    # 3. Фильтр площади
    verdict, priority_flag, area_unknown_flag = get_area_flags(area_m2)
    if verdict == "exclude":
        logger.debug("Исключено по площади ({} м²): {}", area_m2, title[:60])
        return False, False, False

    return True, priority_flag, area_unknown_flag


def get_enabled_directions() -> list[str]:
    """Возвращает список названий включённых направлений (для логов)."""
    cfg = _load_config()
    return [
        d["name"] for d in cfg.get("directions", {}).values()
        if d.get("enabled", False)
    ]
