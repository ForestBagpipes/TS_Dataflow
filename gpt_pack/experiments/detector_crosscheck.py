"""Do independently built detectors also fire on clean unpredictable windows?

Our statistical profile assigns a defect to 65 to 81 percent of the clean_ood
stratum. That is either a weakness of our implementation or a weakness of the
class of signal, and the difference decides whether the paper can claim the
latter. AegisTS would have settled it with its FMMS selected detector, and its
repository cannot be run, so this substitutes several standard off the shelf
detectors instead.

None of these share code with our profile. Three are general purpose outlier
detectors from scikit-learn and two are classical time series methods.

The control that makes this interpretable is the clean stratum, real ETT
windows with nothing injected. A detector that fires on 70 percent of
everything is uninformative. The question is whether the rate on clean but
unpredictable windows is much higher than on clean ordinary ones, and whether
it approaches the rate on genuinely contaminated windows.

CPU only.
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, OOD_KINDS, build_corpus  # noqa: E402

#: A window counts as flagged if this fraction of its points is called
#: anomalous. Chosen to match the sensitivity our own profile has: its spike
#: floor is 0.006, about three points in 512.
FLAG_FRACTION = 0.01


def _win(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 32:
        return None
    s = float(np.std(x))
    return (x - float(np.mean(x))) / (s if s > 1e-12 else 1.0)


def det_isolation_forest(x, rng=0):
    from sklearn.ensemble import IsolationForest
    m = IsolationForest(contamination="auto", random_state=rng, n_estimators=100)
    lab = m.fit_predict(x.reshape(-1, 1))
    return float(np.mean(lab == -1))


def det_lof(x, rng=0):
    from sklearn.neighbors import LocalOutlierFactor
    m = LocalOutlierFactor(n_neighbors=20)
    lab = m.fit_predict(x.reshape(-1, 1))
    return float(np.mean(lab == -1))


def det_ocsvm(x, rng=0):
    from sklearn.svm import OneClassSVM
    m = OneClassSVM(nu=0.05, kernel="rbf", gamma="scale")
    lab = m.fit_predict(x.reshape(-1, 1))
    return float(np.mean(lab == -1))


def det_hampel(x, rng=0):
    """Classical Hampel filter, a rolling median absolute deviation test."""
    from scipy.signal import medfilt
    k = 11
    med = medfilt(x, kernel_size=k)
    resid = np.abs(x - med)
    mad = float(np.median(resid))
    thr = 3.0 * 1.4826 * max(mad, 1e-9)
    return float(np.mean(resid > thr))


def det_zscore(x, rng=0):
    """Plain three sigma on the residual after removing a linear trend."""
    t = np.arange(len(x), dtype=float)
    detr = x - np.poly1d(np.polyfit(t, x, 1))(t)
    s = float(np.std(detr))
    return float(np.mean(np.abs(detr) > 3.0 * max(s, 1e-9)))


DETECTORS = {
    "isolation_forest": det_isolation_forest,
    "local_outlier_factor": det_lof,
    "one_class_svm": det_ocsvm,
    "hampel": det_hampel,
    "zscore_detrended": det_zscore,
}


def main():
    spec = CorpusSpec(n_contaminated=740, n_clean=420, n_hard=210,
                      n_rare_valid=210, n_changepoint=210, n_clean_ood=210,
                      seed=42)
    windows = build_corpus(spec, source="ett")
    oodw = [w for w in windows if w.stratum == "clean_ood"]
    form = {w.window_id: OOD_KINDS[i % len(OOD_KINDS)] for i, w in enumerate(oodw)}

    groups = {"clean": [], "contaminated": [], "hard": []}
    for k in OOD_KINDS:
        groups[f"ood:{k}"] = []
    for w in windows:
        x = _win(w.series)
        if x is None:
            continue
        if w.stratum == "clean_ood":
            groups[f"ood:{form[w.window_id]}"].append(x)
        elif w.stratum in groups:
            groups[w.stratum].append(x)

    print(f"window counts: " + ", ".join(f"{k} {len(v)}" for k, v in groups.items()))
    print(f"a window is flagged when more than {FLAG_FRACTION:.0%} of its points "
          f"are called anomalous\n", flush=True)

    order = ["clean", "hard", "ood:random_walk", "ood:pulse_train",
             "ood:staircase", "ood:sawtooth", "contaminated"]
    out = {}
    header = f"{'detector':22s}" + "".join(f"{k.replace('ood:',''):>14s}" for k in order)
    print(header, flush=True)
    for dname, fn in DETECTORS.items():
        rates = {}
        for g in order:
            flags = []
            for x in groups[g]:
                try:
                    flags.append(fn(x) > FLAG_FRACTION)
                except Exception:
                    flags.append(False)
            rates[g] = float(np.mean(flags)) if flags else float("nan")
        out[dname] = rates
        print(f"{dname:22s}" + "".join(f"{rates[k]:14.3f}" for k in order), flush=True)

    print("\nour profile, from docs/ood_form_split.md, fraction assigned a defect")
    print(f"{'our_statistical_profile':22s}{'-':>14s}{'-':>14s}"
          f"{0.660:14.3f}{0.808:14.3f}{0.755:14.3f}{0.731:14.3f}{'-':>14s}")

    # The binary flag rates above saturate: three of these detectors fire on
    # over 88 percent of real clean ETT windows, so thresholding destroys the
    # signal. The point level rate is the quantity that carries it.
    print("\nmedian fraction of points called anomalous, before thresholding")
    print(header, flush=True)
    point_out = {}
    for dname, fn in DETECTORS.items():
        med = {}
        for g in order:
            vals = []
            for x in groups[g]:
                try:
                    vals.append(fn(x))
                except Exception:
                    pass
            med[g] = float(np.median(vals)) if vals else float("nan")
        point_out[dname] = med
        print(f"{dname:22s}" + "".join(f"{med[k]:14.4f}" for k in order), flush=True)

    print("\nlift over real clean windows, and whether the detector is usable here")
    print(f"{'detector':22s}{'rw lift':>10s}{'pulse lift':>12s}"
          f"{'contam lift':>13s}{'usable':>9s}")
    verdicts = {}
    for dname, med in point_out.items():
        cl = max(med["clean"], 1e-9)
        rw, pt = med["ood:random_walk"] / cl, med["ood:pulse_train"] / cl
        ct = med["contaminated"] / cl
        # A detector that cannot separate contaminated from clean is not
        # measuring data quality on this corpus, so its OOD rate says nothing.
        usable = ct > 1.3
        verdicts[dname] = {"rw_lift": rw, "pulse_lift": pt, "contam_lift": ct,
                           "usable": bool(usable)}
        print(f"{dname:22s}{rw:10.2f}{pt:12.2f}{ct:13.2f}{str(usable):>9s}")

    ok = [d for d, v in verdicts.items() if v["usable"]]
    fired = [d for d in ok if verdicts[d]["rw_lift"] > 1.3
             and verdicts[d]["pulse_lift"] > 1.3]
    print(f"\ndetectors that separate contaminated from clean at all: "
          f"{len(ok)} of {len(point_out)}  {ok}")
    print(f"of those, ones that also fire on both collision free OOD forms: "
          f"{len(fired)}  {fired}")

    (ROOT / "results" / "detector_crosscheck.json").write_text(
        json.dumps({"flag_fraction": FLAG_FRACTION, "window_flag_rates": out,
                    "point_rates": point_out, "lifts": verdicts}, indent=1),
        encoding="utf-8")
    print("___DETECTOR_CROSSCHECK_DONE___")


if __name__ == "__main__":
    main()
