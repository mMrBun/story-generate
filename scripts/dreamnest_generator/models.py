from dataclasses import dataclass


@dataclass(frozen=True)
class StoryType:
    type_id: int
    name: str

    @property
    def slug(self) -> str:
        return f"type_{self.type_id}"


@dataclass(frozen=True)
class StorySummary:
    story_id: int
    title: str
    type_name: str
    length: int
    read_time: str
    short_desc: str
    type_id: int | None = None


@dataclass(frozen=True)
class StoryDetail:
    story_id: int
    title: str
    type_name: str
    length: int
    read_time: str
    content: str
    short_desc: str = ""
    type_id: int | None = None

    @property
    def slug(self) -> str:
        return f"mxnzp-{self.story_id}"
