from .base import PlayerSource
from .afl_tables import AFLTablesSource
from .afl_official import AFLOfficialSource


class PlayerSourceFactory:
    _sources: dict[str, type[PlayerSource]] = {}

    @classmethod
    def register(cls, source_cls: type[PlayerSource]) -> None:
        instance = source_cls()
        cls._sources[instance.name] = source_cls

    @classmethod
    def get(cls, name: str) -> PlayerSource:
        source_cls = cls._sources.get(name)
        if source_cls is None:
            raise KeyError(f"Unknown player source: {name}. Available: {list(cls._sources.keys())}")
        return source_cls()

    @classmethod
    def available_sources(cls) -> list[str]:
        return list(cls._sources.keys())


PlayerSourceFactory.register(AFLTablesSource)
PlayerSourceFactory.register(AFLOfficialSource)


__all__ = [
    "PlayerSource",
    "PlayerSourceFactory",
    "AFLTablesSource",
    "AFLOfficialSource",
]
