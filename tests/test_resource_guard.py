"""
Unit tests for DiscordAutoJoin.resource_guard — domain blocking regex,
CSS optimization injection, and route interception logic.
"""

import re
import pytest

from DiscordAutoJoin.resource_guard import BLOCKED_DOMAINS, OPTIMIZE_CSS


class TestBlockedDomainsRegex:
    """Tests for the BLOCKED_DOMAINS compiled regex pattern."""

    def test_regex_is_compiled(self):
        """BLOCKED_DOMAINS must be a compiled regex pattern."""
        assert isinstance(BLOCKED_DOMAINS, re.Pattern)

    def test_regex_case_insensitive(self):
        """Regex should match regardless of case."""
        assert BLOCKED_DOMAINS.search("https://SENTRY.IO/error")
        assert BLOCKED_DOMAINS.search("https://sentry.io/error")
        assert BLOCKED_DOMAINS.search("https://Sentry.Io/error")

    def test_blocks_sentry(self):
        """Should block sentry.io URLs."""
        assert BLOCKED_DOMAINS.search("https://sentry.io/api/123/store/")
        assert BLOCKED_DOMAINS.search("https://o123.ingest.sentry.io/api/456/")

    def test_blocks_google_analytics(self):
        """Should block google-analytics URLs."""
        assert BLOCKED_DOMAINS.search("https://www.google-analytics.com/collect")
        assert BLOCKED_DOMAINS.search("https://ssl.google-analytics.com/ga.js")

    def test_blocks_googletagmanager(self):
        """Should block googletagmanager URLs."""
        assert BLOCKED_DOMAINS.search("https://www.googletagmanager.com/gtm.js")
        assert BLOCKED_DOMAINS.search("https://googletagmanager.com/gtag/js")

    def test_blocks_doubleclick(self):
        """Should block doubleclick URLs."""
        assert BLOCKED_DOMAINS.search("https://securepubads.g.doubleclick.net/gampad/ads")
        assert BLOCKED_DOMAINS.search("https://doubleclick.net/pixel")

    def test_blocks_newrelic(self):
        """Should block newrelic URLs."""
        assert BLOCKED_DOMAINS.search("https://js-agent.newrelic.com/nr-123.min.js")

    def test_blocks_datadoghq(self):
        """Should block datadoghq URLs."""
        assert BLOCKED_DOMAINS.search("https://logs.datadoghq.com/api/v2/logs")
        assert BLOCKED_DOMAINS.search("https://browser-http-intake.datadoghq.com/")

    def test_blocks_cdn_attachments(self):
        """Should block cdn.discordapp.com/attachments URLs."""
        assert BLOCKED_DOMAINS.search("https://cdn.discordapp.com/attachments/123/456/image.png")

    def test_blocks_media_discordapp(self):
        """Should block media.discordapp.net URLs."""
        assert BLOCKED_DOMAINS.search("https://media.discordapp.net/attachments/123/file.jpg")

    def test_blocks_images_ext(self):
        """Should block images-ext URLs."""
        assert BLOCKED_DOMAINS.search("https://images-ext-1.discordapp.net/external/abc")

    def test_allows_discord_api(self):
        """Should NOT block discord.com API URLs."""
        assert not BLOCKED_DOMAINS.search("https://discord.com/api/v9/gateway")
        assert not BLOCKED_DOMAINS.search("https://discord.com/api/v9/channels/123/messages")

    def test_allows_discord_gateway(self):
        """Should NOT block Discord gateway/websocket URLs."""
        assert not BLOCKED_DOMAINS.search("wss://gateway.discord.gg/?encoding=json")
        assert not BLOCKED_DOMAINS.search("https://discord.com/channels/123/456")

    def test_allows_cdn_non_attachments(self):
        """Should NOT block cdn.discordapp.com non-attachment URLs."""
        # Only /attachments path is blocked, not other CDN paths
        assert not BLOCKED_DOMAINS.search("https://cdn.discordapp.com/icons/123/icon.png")
        assert not BLOCKED_DOMAINS.search("https://cdn.discordapp.com/emojis/456.png")

    def test_allows_blank_url(self):
        """Should NOT match empty or about:blank URLs."""
        assert not BLOCKED_DOMAINS.search("")
        assert not BLOCKED_DOMAINS.search("about:blank")


class TestOptimizeCSS:
    """Tests for the OPTIMIZE_CSS injection string."""

    def test_css_is_string(self):
        """OPTIMIZE_CSS must be a non-empty string."""
        assert isinstance(OPTIMIZE_CSS, str)
        assert len(OPTIMIZE_CSS) > 0

    def test_disables_animations(self):
        """CSS should disable animation-duration."""
        assert "animation-duration: 0s" in OPTIMIZE_CSS

    def test_disables_transitions(self):
        """CSS should disable transition-duration."""
        assert "transition-duration: 0s" in OPTIMIZE_CSS

    def test_hides_gifs(self):
        """CSS should hide GIF-related elements."""
        assert "gif" in OPTIMIZE_CSS.lower()
        assert "visibility: hidden" in OPTIMIZE_CSS

    def test_uses_important(self):
        """CSS should use !important to override Discord styles."""
        assert "!important" in OPTIMIZE_CSS

    def test_targets_all_elements(self):
        """CSS should target universal selector."""
        assert "*" in OPTIMIZE_CSS