"""Public facade for loading EMBED source tables."""

from embed_data_graph.sources.embed.loader import LoadReport, load_embed

__all__ = ["LoadReport", "load_embed"]
