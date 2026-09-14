"""Permanent golden datasets for futures regression tests.

`build.py` holds pure, seeded generators that emit frames in exactly the schema and dtypes
of `data/futures/{ES,MES,NQ,MNQ}.parquet`. Nothing in this package reads `data/`, writes
`data/`, or touches the network: a golden fixture that depends on a live store is not a
fixture, it is a second copy of the thing under test.
"""
