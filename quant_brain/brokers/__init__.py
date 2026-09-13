"""Concrete execution adapters: the only packages allowed to import a broker SDK.

`quant_brain.core.execution` defines the boundary (`ExecutionAdapter`, `RoutedExecutor`).
Everything in here implements it for one venue. Nothing above this package may import
`ib_async` or any other broker library - that is the property that makes a second venue
reachable without editing a trading loop, and it is checkable by grep.

Imports here are lazy on purpose. A research process that never trades must not need the
broker SDK installed to import the package that mentions it.
"""
