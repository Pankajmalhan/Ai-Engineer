"""Shared plain-data types, split out from app/retrieval.py so it and
app/vectorstore.py can both depend on them without importing each other."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Document:
    id: str
    text: str


@dataclass
class RetrievedChunk:
    id: str
    text: str
    score: float
