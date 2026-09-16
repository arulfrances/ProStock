# Standard exchange strike intervals for common indices.
STRIKE_INTERVALS = {
    "NIFTY 50": 50,
    "BANKNIFTY": 100,
    "SENSEX": 100,
}

DEFAULT_INTERVAL = 50


def get_strike_interval(symbol):
    return STRIKE_INTERVALS.get(symbol.upper(), DEFAULT_INTERVAL)


def select_option_strike(symbol, spot_price, side="BUY", moneyness="ATM"):
    """
    Picks a CE/PE strike near the spot price.
    side: BUY -> CE, SELL -> PE
    moneyness: ATM, ITM, OTM (one step, i.e. one strike interval away)
    """
    interval = get_strike_interval(symbol)
    atm_strike = round(spot_price / interval) * interval

    option_type = "CE" if side == "BUY" else "PE"

    if moneyness == "ATM":
        strike = atm_strike
    elif moneyness == "ITM":
        strike = atm_strike - interval if option_type == "CE" else atm_strike + interval
    elif moneyness == "OTM":
        strike = atm_strike + interval if option_type == "CE" else atm_strike - interval
    else:
        strike = atm_strike

    return {
        "strike": int(strike),
        "option_type": option_type,
        "moneyness": moneyness,
        "contract": f"{symbol.replace(' ', '')} {int(strike)} {option_type}",
    }
