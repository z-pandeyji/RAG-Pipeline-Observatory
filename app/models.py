from dataclasses import dataclass, field


@dataclass
class DocumentChunk:
    chunk_id: str
    page_start: int
    page_end: int
    text: str
    token_estimate: int


@dataclass
class PipelineTrace:
    stage: str
    metrics: dict = field(default_factory=dict)
