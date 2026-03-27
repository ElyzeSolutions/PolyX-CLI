"""Test noise filtering."""

from polyx.analysis.noise import is_promotional_noise


def test_is_promotional_noise():
    # Promotional noise (2+ tokens)
    assert is_promotional_noise("Join my telegram for free signals 99% accuracy") is True
    # Promotional noise (link + telegram + 1 token)
    assert is_promotional_noise("Check out my VIP signal at https://t.me/cryptogroup") is True

    # Legitimate tweets
    assert is_promotional_noise("Bitcoin price is up 5% today.") is False
    assert is_promotional_noise("Thinking about the future of AI agents.") is False
    assert is_promotional_noise("Breaking news from the FED.") is False
