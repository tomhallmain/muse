"""Pure logic for choosing DJ introduction type from persona timing."""

import datetime
from typing import Any

from utils.globals import IntroType
from utils.logging_setup import get_logger

logger = get_logger(__name__)


def determine_intro_type(now_time: float, persona: Any) -> IntroType:
    """Decide whether the DJ should give an intro, reintro, or stay silent."""
    last_hello = persona.last_hello_time or 0
    last_signoff = persona.last_signoff_time or 0

    if (
        last_hello == 0
        or last_signoff == 0
        or (now_time - last_hello > 6 * 3600 and now_time - last_signoff > 6 * 3600)
    ):
        logger.debug(
            "intro case 1: last_hello: {0}, last_signoff: {1}, now_time: {2}".format(
                last_hello, last_signoff, now_time
            )
        )
        return IntroType.INTRO

    last_signoff_dt = datetime.datetime.fromtimestamp(last_signoff)
    now_dt = datetime.datetime.fromtimestamp(now_time)

    if (
        (4 * 3600) < (now_time - last_signoff) < (12 * 3600)
        and (
            (last_signoff_dt.hour >= 23 or last_signoff_dt.hour < 6)
            and (now_dt.hour > 4 and now_dt.hour < 10)
        )
    ):
        logger.debug(
            "intro case 2: last_hello: {0}, last_signoff: {1}, now_time: {2}".format(
                last_hello, last_signoff, now_time
            )
        )
        return IntroType.INTRO

    if now_time - last_hello > 2 * 3600 and 1 * 3600 < now_time - last_signoff <= 6 * 3600:
        logger.debug(
            "reintro: last_hello: {0}, last_signoff: {1}, now_time: {2}".format(
                last_hello, last_signoff, now_time
            )
        )
        return IntroType.REINTRO

    logger.debug(
        "no intro: last_hello: {0}, last_signoff: {1}, now_time: {2}".format(
            last_hello, last_signoff, now_time
        )
    )
    return IntroType.NONE
