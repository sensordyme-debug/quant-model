"""In-process fakes for the execution path.

Nothing in this package opens a socket, reads a credential or imports a broker SDK. A fake
here is a stand-in that can be made to MISBEHAVE - reject, half-fill, echo a fill, lose a
fill, or hold a position the local book never opened - because a stub that agrees with
everything proves only that the code compiles.
"""
