import data_handler
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import jarque_bera
from scipy.stats import norm
from scipy.optimize import minimize


def semi_deviation(r):
    is_negative = r < 0
    return r[is_negative].std(ddof=0)


def var_historic(r, level=5):
    """
    In this approach we calculate VaR directly from past returns.
    For example, suppose we want to calculate the 1-day 95% VaR for an equity using 100 days of data.
    The 95th percentile corresponds to the least worst of the worst 5% of returns.
    In this case, because we are using 100 days of data, the VaR simply corresponds to the 5th worst day.
    "How much could I lose in a really bad day?"
    """
    if isinstance(r, pd.DataFrame):
        return r.aggregate(var_historic, level=level)
    elif isinstance(r, pd.Series):
        return -np.percentile(r, level)
    else:
        raise TypeError("Expected r to be pd.DataFrame or pd.Series!")


def cvar_historic(r, level=5):
    """
    Computes the Conditional VaR of pd.Series of pd.DataFrame.
    """
    if isinstance(r, pd.Series):
        is_beyond = r <= -var_historic(r, level=level)
        return -r[is_beyond].mean()
    elif isinstance(r, pd.DataFrame):
        return r.aggregate(cvar_historic, level=level)
    else:
        raise TypeError("Expected r to be pd.DataFrame or pd.Series!")


def var_gaussian(r, level=5, modified=False):
    """
    Returns Parametric Gaussian VaR of a pd.Series of pd.DataFrame.
    If "modified" is set to True, then the modified VaR is returned, using the Cornish-Fisher modification.
    mVaR represents an empirical expression adjusted for skewness and kurtosis of the empirical distribution.
    Empirical returns are commonly skewed and peaked, such that assuming normal distribution is a bad fit to estimate VaR.
    Therefore, mVaR adjusts for skewness and kurtosis to better reflect the empirical VaR.
    """
    z = norm.ppf(level/100)
    if modified:
        # Modify the z score based on observed skewness and kurtosis
        s = skewness(r)
        k = kurtosis(r)
        z = (z + (z**2-1)*s/6 + (z**3-3*z)*(k-3)/24 - (2*z**3-5*z)*(s**2)/36)
    return -(r.mean() + z*r.std(ddof=0))


def skewness(r):
    """
    Alternative to scipy.stats.skew()

    Args:
        r (:obj: pd.Seried):

    Returns:
        float or pd.Seried
    """
    demeaned_r = r - r.mean()
    # Population standard deviation
    sigma_r = r.std(ddof=0)
    exp = (demeaned_r**3).mean()
    return exp/sigma_r**3


def kurtosis(r):
    """
    Alternative to scipy.stats.kurtosis()

    Args:
        r (:obj: pd.Seried):

    Returns:
        float or pd.Seried
    """
    demeaned_r = r - r.mean()
    # Population standard deviation
    sigma_r = r.std(ddof=0)
    exp = (demeaned_r**4).mean()
    return exp/sigma_r**4


def is_normal(r, level=0.01):
    """
    Applies the Jarque-Bera test to determine if a pd.Series is normal or not.
    Test is applied at 1% level by default.
    Returns True if the hypothesis of normality is accepted, False otherwise.
    """
    statistic, p_value = jarque_bera(r)
    return p_value > level


def annualise_rets(r, periods_per_year):
    compounded_growth = (1+r).prod()
    n_periods = r.shape[0]
    return compounded_growth**(periods_per_year/n_periods)-1


def annualise_vol(r, periods_per_year):
    return r.std()*(periods_per_year**0.5)


def sharpe_ratio(r, risk_free_rate, periods_per_year):
    # Convert annual risk free rate to per period
    rf_per_period = (1+risk_free_rate)*(1/periods_per_year)-1
    excess_ret = r - rf_per_period
    ann_ex_ret = annualise_rets(excess_ret, periods_per_year)
    ann_vol = annualise_vol(r, periods_per_year)
    return ann_ex_ret/ann_vol


def drawdown(return_series, cash=1000):
    """
    Args:
        return_series (:obj: pd.DataFrame):

    Returns:
        wealth (:obj: pd.DataFrame)
        peaks (:obj: pd.DataFrame)
        drawdown (:obj: pd.DataFrame)
    """
    wealth_index = cash*(return_series+1).cumprod()
    previous_peak = wealth_index.cummax()
    drawdowns = (wealth_index-previous_peak)/previous_peak
    return pd.DataFrame({
        "wealth": wealth_index,
        "peaks": previous_peak,
        "drawdown": drawdowns
    })


def portfolio_return(weights, returns):
    return weights.T @ returns


def portfolio_vol(weights, covmat):
    return (weights.T @ covmat @ weights)**0.5


def plot_binary_efficient_frontier(n_points, er, cov):
    if er.shape[0] != 2 or cov.shape[0] != 2:
        raise ValueError("plot_efficient_frontier_2 can only plot 2-asset frontiers!")
    weights = [np.array([w, 1-w]) for w in np.linspace(0, 1, n_points)]
    rets = [portfolio_return(w, er) for w in weights]
    vols = [portfolio_vol(w, cov) for w in weights]
    ef = pd.DataFrame({"Returns": rets, "Volatility": vols})
    plt.figure(figsize=(15, 10))
    plt.scatter(ef.Volatility, ef.Returns)
    plt.show()


def minimize_vol(target_return, er, cov):
    n = er.shape[0]
    init_guess = np.repeat(1/n, n)
    bounds = ((0.0, 1.0), )*n
    return_is_target = {
        "type": "eq",
        "args": (er, ),
        "fun": lambda weights, er: target_return - portfolio_return(weights, er)
    }
    weights_sum_to_one = {
        "type": "eq",
        "fun": lambda weights: np.sum(weights) - 1
    }
    results = minimize(
        portfolio_vol,
        init_guess,
        args=(cov, ),
        method="SLSQP",
        options={"disp": False},
        constraints=(return_is_target, weights_sum_to_one),
        bounds=bounds)
    return results.x


def optimal_weights(n_points, er, cov):
    target_rs = np.linspace(er.min(), er.max(), n_points)
    weights = [minimize_vol(target_return, er, cov) for target_return in target_rs]
    return weights


def plot_multi_efficient_frontier(n_points, er, cov):
    weights = optimal_weights(n_points, er, cov)
    rets = [portfolio_return(w, er) for w in weights]
    vols = [portfolio_vol(w, cov) for w in weights]
    ef = pd.DataFrame({"Returns": rets, "Volatility": vols})
    plt.figure(figsize=(15, 10))
    plt.scatter(ef.Volatility, ef.Returns)
    plt.show()


def main():
    data1 = data_handler.read_stock_table_from_db("GOOG").Close
    data2 = data_handler.read_stock_table_from_db("AAPL").Close
    data3 = data_handler.read_stock_table_from_db("MSFT").Close
    data4 = data_handler.read_stock_table_from_db("AMZN").Close
    data = pd.concat([data1, data2, data3, data4], axis=1, join="inner")
    data.columns = ["GOOG", "AAPL", "MSFT", "AMZN"]
    returns = data.pct_change()
    er = annualise_rets(returns, periods_per_year=252)
    cov = returns.cov()
    w15 = minimize_vol(0.15, er, cov)
    vol15 = portfolio_vol(w15, cov)
    print(w15)
    print(vol15)
    plot_multi_efficient_frontier(200, er, cov)


if __name__ =="__main__":
    main()
