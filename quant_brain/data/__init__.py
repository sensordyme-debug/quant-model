"""The canonical market-data layer.

Nothing outside `adapters` may know a provider's column names, and nothing may enter
research without a declared `DataForm`. See `docs/DATA_FLOW_FORENSICS.md` for the state
this layer replaces and why each refusal exists.
"""
