"""Statistical profiling: extract a 12-dimensional feature vector from a univariate time series.

The profile describes the *external* properties of a window (trend, seasonality,
stationarity, complexity, changepoints, tails). It never looks at the model. It
serves two purposes in IntroAct-TS: it defines the peer group a window is
calibrated against, and it feeds the risk state that drives action choice.

All features are computed without any file IO. Input: numpy array (T,).
Output: numpy array (12,). Order is documented and MUST NOT change.
"""

import numpy as np
from scipy import fft
from scipy.stats import linregress
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import adfuller
from statsmodels.stats.diagnostic import acorr_ljungbox
import ruptures as rpt


def _safe_divide(a, b, default=0.0):
    denom = np.where(b == 0, np.nan, b)
    result = np.divide(a, denom)
    result = np.where(np.isnan(result), default, result)
    result = np.where(np.isinf(result), default, result)
    return float(result)


def extract_statistical_profile(series: np.ndarray) -> np.ndarray:
    """Extract a 12-dimensional statistical profile from a univariate time series.

    Dimension order (fixed, do not change):
      0: trend_strength       OLS R^2 of linear fit
      1: trend_linearity      ratio of linear R^2 to quadratic R^2
      2: seasonality_strength dominant FFT frequency energy ratio
      3: seasonality_stability std of sliding-window seasonal correlations
      4: stationarity          ADF test p-value
      5: sample_entropy        approximate sample entropy
      6: changepoint_density   PELT changepoints per unit length
      7: changepoint_magnitude mean absolute change at detected changepoints
      8: residual_autocorr_l1  Ljung-Box Q statistic at lag 1 on STL residuals
      9: residual_autocorr_l7  Ljung-Box Q statistic at lag 7 on STL residuals
     10: signal_to_noise_ratio signal variance / residual variance
     11: anomaly_density       fraction of points outside 3*IQR from median

    Args:
        series: 1D numpy array of float. Length must be >= 24 for STL.

    Returns:
        profile: numpy array of shape (12,) with float values.
    """
    T = len(series)
    series = np.asarray(series, dtype=np.float64)
    profile = np.zeros(12, dtype=np.float64)

    # 0: trend_strength -- OLS R^2 of linear fit
    t = np.arange(T, dtype=np.float64)
    slope, intercept, r_value, p_value, std_err = linregress(t, series)
    profile[0] = r_value ** 2

    # 1: trend_linearity -- ratio of linear R^2 to quadratic R^2
    t2 = np.column_stack([np.ones(T), t, t * t])
    coeffs_quad, residuals_quad, _, _ = np.linalg.lstsq(t2, series, rcond=None)
    ss_res_quad = np.sum(residuals_quad ** 2)
    ss_tot = np.sum((series - np.mean(series)) ** 2)
    r2_quad = 1.0 - _safe_divide(ss_res_quad, ss_tot, 0.0)
    profile[1] = _safe_divide(profile[0], r2_quad, 1.0)

    # STL decomposition (period defaults to 7 for daily/weekly, but we use a heuristic)
    period = max(7, min(T // 4, 168))
    try:
        stl = STL(series, period=period, robust=True).fit()
        trend = stl.trend
        seasonal = stl.seasonal
        residual = stl.resid
    except Exception:
        trend = np.zeros(T)
        seasonal = np.zeros(T)
        residual = series

    # 2: seasonality_strength -- dominant FFT frequency energy ratio
    if T >= 8:
        fft_vals = np.abs(fft.rfft(series - np.mean(series)))
        freqs = fft.rfftfreq(T)
        low_mask = (freqs > 0) & (freqs <= 0.5)
        if low_mask.sum() > 0:
            valid_fft = fft_vals[low_mask]
            top_idx = np.argmax(valid_fft)
            peak_energy = valid_fft[top_idx]
            total_energy = np.sum(valid_fft)
            profile[2] = _safe_divide(peak_energy, total_energy, 0.0)
        else:
            profile[2] = 0.0
    else:
        profile[2] = 0.0

    # 3: seasonality_stability -- std of sliding-window seasonal correlations
    if T >= period * 4 and np.std(seasonal) > 1e-10:
        win = period * 2
        n_windows = T // win
        if n_windows >= 3:
            corrs = []
            for w in range(n_windows - 1):
                s1 = seasonal[w * win:(w + 1) * win]
                s2 = seasonal[(w + 1) * win:(w + 2) * win]
                c = np.corrcoef(s1, s2)[0, 1]
                if not np.isnan(c):
                    corrs.append(c)
            if corrs:
                profile[3] = float(np.std(corrs))
            else:
                profile[3] = 0.0
        else:
            profile[3] = 0.0
    else:
        profile[3] = 0.0

    # 4: stationarity -- ADF test p-value
    try:
        adf_result = adfuller(series, maxlag=min(12, T // 4), autolag="AIC")
        profile[4] = float(adf_result[1])
    except Exception:
        profile[4] = 0.0

    # 5: sample_entropy -- approximate sample entropy (m=2, fast variant)
    try:
        m = 2
        r_factor = 0.2 * np.std(series)
        if r_factor > 0 and T >= 10:
            def _count_matches_fast(data, m_val, r_val):
                N = len(data)
                count = 0
                templates = np.array([data[i:i + m_val] for i in range(N - m_val)])
                for i in range(min(N - m_val, 80)):  # subsample for speed
                    template = templates[i]
                    dists = np.max(np.abs(templates - template), axis=1)
                    count += np.sum(dists < r_val)
                return max(count, 1)
            A = _count_matches_fast(series, m + 1, r_factor)
            B = _count_matches_fast(series, m, r_factor)
            profile[5] = -np.log(_safe_divide(float(A), float(B), 1.0))
        else:
            profile[5] = 0.0
    except Exception:
        profile[5] = 0.0

    # 6, 7: changepoint_density and changepoint_magnitude via PELT
    try:
        if T >= 10:
            algo = rpt.Pelt(model="rbf", min_size=5).fit(series)
            bkps = algo.predict(pen=10)
            bkps = [b for b in bkps if b < T]
            profile[6] = float(len(bkps)) / float(T) if T > 0 else 0.0
            if len(bkps) > 0:
                mags = []
                prev = 0
                for b in bkps:
                    if b > prev:
                        mags.append(abs(np.mean(series[prev:b]) - np.mean(series[b:min(b + 1, T)])))
                    prev = b
                profile[7] = float(np.mean(mags)) if mags else 0.0
            else:
                profile[7] = 0.0
        else:
            profile[6] = 0.0
            profile[7] = 0.0
    except Exception:
        profile[6] = 0.0
        profile[7] = 0.0

    # 8, 9: residual autocorrelation (Ljung-Box at lags 1 and 7)
    try:
        if T >= 10:
            lb_result = acorr_ljungbox(residual, lags=[1, 7], return_df=True)
            profile[8] = float(lb_result["lb_stat"].iloc[0]) if len(lb_result) > 0 else 0.0
            profile[9] = float(lb_result["lb_stat"].iloc[1]) if len(lb_result) > 1 else 0.0
        else:
            profile[8] = 0.0
            profile[9] = 0.0
    except Exception:
        profile[8] = 0.0
        profile[9] = 0.0

    # 10: signal_to_noise_ratio
    sig_var = np.var(series)
    noise_var = np.var(residual) if np.var(residual) > 1e-10 else 1e-10
    profile[10] = _safe_divide(sig_var, noise_var, 0.0)

    # 11: anomaly_density -- fraction outside 3*IQR
    q1, q3 = np.percentile(series, [25, 75])
    iqr_val = q3 - q1
    if iqr_val > 0:
        lower = q1 - 3.0 * iqr_val
        upper = q3 + 3.0 * iqr_val
        profile[11] = float(np.sum((series < lower) | (series > upper))) / float(T)
    else:
        profile[11] = 0.0

    return profile.astype(np.float64)
