"""
YVid — package ``__main__`` launcher.

Run ``python -m yvid`` to launch the Terminal CLI.
Run ``yvid-gui`` to launch the Desktop GUI.
"""

from .cli import main as cli_main

cli_main()
