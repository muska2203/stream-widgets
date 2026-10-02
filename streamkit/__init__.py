"""streamkit: building blocks for Twitch-interactive stream overlay apps.

Core (this package) has no heavy dependencies: chat sources, voting and
config loading are plain Python. Ursina-based overlay helpers live in
`streamkit.overlay` and are imported explicitly; `twitchio` is imported
lazily by `streamkit.chat.TwitchChat`.
"""

from streamkit.chat import MockChat, TwitchChat
from streamkit.chatters import ChatterRegistry
from streamkit.config import load_env, load_toml_config
from streamkit.paths import bundled_defaults_dir, bundled_dir, frozen_app_dir
from streamkit.voting import VoteLoop, VotingRound
from streamkit.votewords import VoteWords

__all__ = ["MockChat", "TwitchChat", "ChatterRegistry", "load_env",
           "load_toml_config", "VoteLoop", "VotingRound", "VoteWords",
           "bundled_defaults_dir", "bundled_dir", "frozen_app_dir"]
