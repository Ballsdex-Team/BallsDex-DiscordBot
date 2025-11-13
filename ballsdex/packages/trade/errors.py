import logging

from ballsdex.settings import settings

log = logging.getLogger("ballsdex.packages.trade")


class TradeError(RuntimeError):
    """
    User-facing exceptions while trading. You can obtain a friendly error using the `error_message` function.
    """

    msg: str | None = None

    @property
    def error_message(self) -> str:
        if self.msg is None:
            log.error("Unknown error during trade", exc_info=self)
            return "An unknown exception occured. Contact support if this persists."
        return self.msg


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

    msg = f"This {settings.collectible_name} is not tradeable."


class AlreadyLockedError(TradeError):
    """
    Raised when a locked countryball is about to be traded.
    """

    msg = (
        f"This {settings.collectible_name} has been locked in a different trade. "
        "Remove it from your other trade or wait for it to timeout (30 min)"
    )


class NotProposedError(TradeError):
    """
    A countryball was attempted to be removed when it was not part of the proposal.
    """

    msg = f"This {settings.collectible_name} is not part of your proposal and cannot be removed."


class OwnershipError(TradeError):
    """
    A countryball is attempting to be traded, but it's not owned by the player.
    """

    msg = f"You do not own this {settings.collectible_name}."


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
