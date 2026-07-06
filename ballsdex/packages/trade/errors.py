import logging

from ballsdex.core.translation import t
from settings.models import settings

log = logging.getLogger("ballsdex.packages.trade")


class TradeError(RuntimeError):
    """
    User-facing exceptions while trading. You can obtain a friendly error using the `error_message` function.
    """

    msg: str | None = None

    @property
    def error_message(self) -> str:
        # translated (and, for some subclasses, formatted with the collectible name) here, at
        # access time, rather than where `msg` is set on each subclass - a class-level attribute
        # resolved once at import time, when `settings.collectible_name` may not even reflect
        # the operator's configured value yet, and no interaction locale is known
        if self.msg is None:
            log.error("Unknown error during trade", exc_info=self)
            return t("An unknown exception occurred. Contact support if this persists.")
        return t(self.msg).format(collectible=settings.collectible_name)


class LockedError(TradeError):
    """
    Raised when a player attempts to edit a locked proposal
    """

    msg = "You cannot edit your proposal after it has been locked!"


class CancelledError(TradeError):
    """
    The trade has been cancelled and does not accept operations. Should not happen other than a few race conditions.
    """

    msg = "This trade has been cancelled."


class NotTradeableError(TradeError):
    """
    The countryball is not tradeable (ball, ballinstance or special)
    """

    msg = "This {collectible} is not tradeable."


class AlreadyLockedError(TradeError):
    """
    Raised when a locked countryball is about to be traded.
    """

    msg = (
        "This {collectible} has been locked in a different trade. "
        "Remove it from your other trade or wait for it to timeout (30 min)"
    )


class NotProposedError(TradeError):
    """
    A countryball was attempted to be removed when it was not part of the proposal.
    """

    msg = "This {collectible} is not part of your proposal and cannot be removed."


class OwnershipError(TradeError):
    """
    A countryball is attempting to be traded, but it's not owned by the player.
    """

    msg = "You do not own this {collectible}."


class IntegrityError(TradeError):
    """
    An attempt to cheat is being detected, which must cancel the trade.
    This happens when the ownership of the countryball changes while processing the trade.
    """

    msg = "An attempt to modify the trade has been detected, the trade is cancelled to prevent cheating."


class SynchronizationError(TradeError):
    """
    The trade is being attempted to confirm twice.
    Receiving this error means the trading operation has already started or has finished already.
    """

    msg = "The trade is already confirmed and being applied. Please wait until the message updates."
